import asyncio
import datetime
import http
import os

import aiohttp
import tenacity
import yarl
from dateutil import parser
from ruamel.yaml import YAML
from tenacity import retry, stop_after_attempt
from pathlib import Path

REPOS_FILE = f'{os.curdir}/config.yaml'


@retry(stop=stop_after_attempt(10))
async def api_call(
        session: aiohttp.ClientSession, path: str,
        payload: dict = None, method='POST', query: dict = None, headers: dict = None,
) -> dict:
    try:
        url = yarl.URL(path)
        if method == 'POST':
            req_f = session.post
        elif method == 'GET':
            req_f = session.get
        else:
            raise Exception('request method {} not supported'.format(method))

        async with req_f(
                url.with_query(query),
                headers=headers,
                json=payload,
        ) as response:
            body = await response.json()
            if response.status != http.HTTPStatus.OK:
                raise RuntimeError(path, body, response.status)
            return body

    except Exception:
        raise


async def get_all_merge_request(session: aiohttp.ClientSession, project_id: int):
    res = await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests',
        method='GET',
        query={'per_page': 100, 'page': 1, 'state': 'opened'},
    )
    return res


async def get_eligible_approvers(session: aiohttp.ClientSession, project_id: int):
    res = await api_call(
        session,
        f'/api/v4/projects/{project_id}/approval_rules',
        method='GET',
    )
    return res


async def get_current_user(session: aiohttp.ClientSession):
    res = await api_call(
        session,
        f'/api/v4/user',
        method='GET',
    )
    return res


async def get_approvals(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    res = await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals',
        method='GET',
    )
    return res


async def get_discussions(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    res = await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions',
        method='GET',
        query={'per_page': 100, 'page': 1, 'state': 'opened'},
    )
    return res


async def async_main():
    # parser = ArgumentParser()
    # parser.add_argument('--config', dest='config', help='path to config file')
    # args = parser.parse_args()

    config_path = os.path.join(str(Path.home()), 'pymr-config.yaml')
    if not os.path.exists(config_path):
        print(f'config file does not exist at {config_path}')
        return 1

    yaml = YAML()
    with open(config_path) as f:
        config = yaml.load(f)['config']

    projects = [x['id'] for x in config['projects'].values()]

    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=0, ssl=False),
            base_url=yarl.URL(config['gitlab']),
            headers={'Private-Token': config['token']}
    ) as session:
        data = {}

        async def collect_project_data(project_id):
            try:
                all_mrs, eligible_approvers = await asyncio.gather(
                    get_all_merge_request(session, project_id),
                    get_eligible_approvers(session, project_id)
                )
            except tenacity.RetryError as ex:
                print(ex.last_attempt.exception())
                return

            data[project_id] = {}
            data[project_id]['mrs'] = {x['iid']: {'mr': x} for x in all_mrs}
            data[project_id]['approvers'] = eligible_approvers

        await asyncio.gather(*(collect_project_data(x) for x in projects))

        if not data:
            print('No data found, check config and try again')
            return 1

        project_mr_iids = {proj_id: [mr_iid for mr_iid in proj['mrs']] for proj_id, proj in data.items()}

        async def collect_mr_data(project_id, mr_iids):
            discussions, approvals = await asyncio.gather(
                asyncio.gather(*(get_discussions(session, project_id, mr_iid) for mr_iid in mr_iids)),
                asyncio.gather(*(get_approvals(session, project_id, mr_iid) for mr_iid in mr_iids)),
            )
            for i in range(len(mr_iids)):
                mr_iid = mr_iids[i]
                data[project_id]['mrs'][mr_iid].update({'approvals': approvals[i], 'discussions': discussions[i]})

        await asyncio.gather(
            *(collect_mr_data(project_id, mr_iids) for project_id, mr_iids in project_mr_iids.items() if mr_iids)
        )

    report = []
    for project in data.values():
        if not project['mrs']:
            continue

        for mr in project['mrs'].values():
            unresolved_threads = [
                [n for n in d['notes'] if n['resolvable'] and not n['resolved']] for d in mr['discussions']
            ]
            unresolved_count = len([x for x in unresolved_threads if x])
            info = {
                'web_url': mr['mr']['web_url'],
                'title': mr['mr']['title'],
                'author_username': mr['mr']['author']['username'],
                'has_conflicts': mr['mr']['has_conflicts'],
                'approvals':
                    [x for x in [x.get('user', {}).get('username') for x in mr['approvals']['approved_by']] if x],
                'created_at': parser.parse(mr['mr']['created_at']),
                'updated_at': parser.parse(mr['mr']['updated_at']),
                'unresolved_count': unresolved_count,
            }
            report.append(info)

    render_report(sorted(report, key=lambda x: x['created_at']))


def render_report(report: list):
    all_approvers = set()
    for r in report:
        for a in r['approvals']:
            all_approvers.add(a)
    max_approver_len = max(len(x) for x in all_approvers)

    for r in report:
        age_days = (datetime.datetime.utcnow() - r['created_at'].replace(tzinfo=None)).days

        developer = '👨‍💻'
        if age_days > 10:
            developer = '💀'

        caption = [
            f"""{developer}{r['author_username']:<{max_approver_len}}""", f"""{age_days:>3}d"""
        ]

        flags = []
        if r['unresolved_count']:
            flags.append(str(r['unresolved_count']) + ' 💬')
        if not r['approvals'] and not r['unresolved_count'] and not r['has_conflicts']:
            flags.append('⏳')
        if r['has_conflicts']:
            flags.append('🛑')
        if not flags:
            flags.append('⏳')

        caption.append(f"""{' '.join(flags):>4}""")

        link_title = f"""{r['title'][:70]:<70}"""
        caption.append(f"""{link(r['web_url'], link_title):<70}""")

        if r['approvals']:
            caption.append(f"""✅ {', '.join(r['approvals'])}""")
        else:
            caption.append('')

        print(' | '.join(caption))


def link(url, text):
    return '\x1b]8;;' + url + '\x1b\\' + text + '\x1b]8;;\x1b\\'


def main():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(async_main())


if __name__ == '__main__':
    main()
