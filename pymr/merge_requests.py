import asyncio
import datetime
import http
import os
from argparse import ArgumentParser
from collections import OrderedDict
from pathlib import Path
from typing import Set

import aiohttp
import tenacity
import yarl
from aiohttp import client_exceptions
from dateutil import parser as dt_parser
from ruamel.yaml import YAML
from tenacity import retry, stop_after_attempt


def red(text): return f'\033[91m{text}\033[00m'


def green(text): return f'\033[92m{text}\033[00m'


def yellow(text): return f'\033[93m{text}\033[00m'


def light_purple(text): return f'\033[94m{text}\033[00m'


def purple(text): return f'\033[95m{text}\033[00m'


def cyan(text): return f'\033[96m{text}\033[00m'


def light_gray(text): return f'\033[97m{text}\033[00m'


def link(url, text): return f'\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\'


def subscript(i: int):
    # if i > 10:
    #     i = 10
    # return f"{chr(0x2080 + i)}"
    return str(i) if i < 10 else '+'


def bold(s: str):
    return f"""\033[1m{s}\033[0m"""


@retry(stop=stop_after_attempt(1))
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


async def get_all_merge_requests(session: aiohttp.ClientSession, project_id: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests',
        method='GET',
        query={'per_page': 100, 'page': 1, 'state': 'opened'},
    )


async def get_eligible_approvers(session: aiohttp.ClientSession, project_id: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/approval_rules',
        method='GET',
    )


async def get_current_user(session: aiohttp.ClientSession):
    return await api_call(
        session,
        f'/api/v4/user',
        method='GET',
    )


async def get_approvals(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals',
        method='GET',
    )


async def get_discussions(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions',
        method='GET',
        query={'per_page': 100, 'page': 1, 'state': 'opened'},
    )


async def get_commits(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}/commits',
        method='GET',
        query={'per_page': 100, 'page': 1, 'state': 'opened'},
    )


async def get_mr_info(session: aiohttp.ClientSession, project_id: int, mr_iid: int):
    return await api_call(
        session,
        f'/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
        method='GET',
    )


async def async_main():
    parser = ArgumentParser()
    parser.add_argument('--skip-approved-by-me', action='store_true', help='skip MRs approved by me')
    parser.add_argument('--my', action='store_true', default=False, help='show only MRs created by me')
    args = parser.parse_args()

    config_path = os.path.join(str(Path.home()), 'pymr-config.yaml')
    if not os.path.exists(config_path):
        print(f'config file does not exist at {config_path}')
        return 1

    yaml = YAML()
    with open(config_path) as f:
        config = yaml.load(f)['config']

    robots = {x for x in config['robots']}

    group_settings = {group_name: {k: v} for group_name, group in config['groups'].items() for k, v in group.items() if
                      k != 'projects'}

    projects = {proj['id']: group_name for group_name, group in config['groups'].items() for proj in
                group['projects'].values()}

    project_names = {proj['id']: name for group_name, group in config['groups'].items() for name, proj in
                     group['projects'].items()}

    groups = [x for x in config['groups']]

    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=0, ssl=False),
            base_url=yarl.URL(config['gitlab']),
            headers={'Private-Token': config['token']}
    ) as session:
        data = {}

        current_user = await get_current_user(session)

        async def collect_project_data(project_id):
            try:
                all_mrs, elig_approvers = await asyncio.gather(
                    get_all_merge_requests(session, project_id),
                    get_eligible_approvers(session, project_id)
                )
            except tenacity.RetryError as ex:
                print(ex.last_attempt.exception())
                return

            data[project_id] = {}
            data[project_id]['mrs'] = {x['iid']: {'mr': x} for x in all_mrs}
            data[project_id]['approvers'] = elig_approvers

        await asyncio.gather(*(collect_project_data(x) for x in projects))

        if not data:
            print('No data found, check config and try again')
            return 1

        project_mr_iids = {proj_id: [mr_iid for mr_iid in proj['mrs']] for proj_id, proj in data.items()}

        async def collect_mr_data(project_id, mr_iids):
            discussions, approvals, commits, mr_infos = await asyncio.gather(
                asyncio.gather(*(get_discussions(session, project_id, mr_iid) for mr_iid in mr_iids)),
                asyncio.gather(*(get_approvals(session, project_id, mr_iid) for mr_iid in mr_iids)),
                asyncio.gather(*(get_commits(session, project_id, mr_iid) for mr_iid in mr_iids)),
                asyncio.gather(*(get_mr_info(session, project_id, mr_iid) for mr_iid in mr_iids)),
            )
            for idx in range(len(mr_iids)):
                mr_iid = mr_iids[idx]
                data[project_id]['mrs'][mr_iid].update({
                    'approvals': approvals[idx],
                    'discussions': discussions[idx],
                    'commits': commits[idx],
                    'mr_info': mr_infos[idx],
                })

        await asyncio.gather(
            *(collect_mr_data(project_id, mr_iids) for project_id, mr_iids in project_mr_iids.items() if mr_iids)
        )

    reports = OrderedDict()

    for project_id, project in data.items():
        if not project['mrs']:
            continue

        eligible_approvers = set()
        for i in project['approvers']:
            if i['name'] != 'Owner':
                continue
            for a in i['eligible_approvers']:
                eligible_approvers.add(a['username'])

        for mr in project['mrs'].values():
            unresolved_threads = [
                [n for n in d['notes'] if n['resolvable'] and not n['resolved']] for d in mr['discussions']
            ]
            unresolved_count = len([x for x in unresolved_threads if x])

            author_username = mr['mr']['author']['username']
            if mr['commits']:
                author_username = mr['commits'][-1]['author_email'].split('@')[0]

            info = {
                'web_url': mr['mr']['web_url'],
                'project_name': project_names[mr['mr']['project_id']],
                'title': mr['mr']['title'],
                'author_username': author_username,
                'has_conflicts': mr['mr']['has_conflicts'],
                'approvals':
                    [x for x in [x.get('user', {}).get('username') for x in mr['approvals']['approved_by']] if x],
                'created_at': dt_parser.parse(mr['mr']['created_at']),
                'updated_at': dt_parser.parse(mr['mr']['updated_at']),
                'unresolved_count': unresolved_count,
                'eligible_approvers': eligible_approvers,
                'current_user': current_user['username'],
                'pipeline_status': (mr.get('mr_info', {}).get('pipeline', {}) or {}).get('status'),
            }
            group = projects[project_id]

            show_only_my = args.my | group_settings.get(group, dict()).get('show_only_my', False)

            if show_only_my and info['author_username'] != info['current_user']:
                continue

            skip_mr = False
            if info['approvals']:
                for a in info['approvals']:
                    if args.skip_approved_by_me and a == info['current_user']:
                        skip_mr = True
            if skip_mr:
                continue

            if group not in reports:
                reports[group] = []

            reports[group].append(info)

    for group in groups:
        if group not in reports:
            continue

        print(yellow(bold(group)))
        render_group_report(
            sorted(reports[group], key=lambda x: x['created_at']),
            robots=robots,
        )


def render_group_report(report: list, robots: Set[str] = None):
    all_authors = set()
    for r in report:
        all_authors.add(r['author_username'])
    max_author_name_len = max(len(x) for x in all_authors)

    for r in report:
        age_days = (datetime.datetime.utcnow() - r['created_at'].replace(tzinfo=None)).days

        author = r['author_username']
        author_avatar = '👨‍'
        if age_days > 10:
            author_avatar = '💀'
        if author in robots:
            author_avatar = '🤖'

        max_author_name_len = min(12, max_author_name_len)

        author_name = r['author_username'][:max_author_name_len]
        own_mr = author_name == r['current_user']
        if own_mr:
            author_name = green(author_name) + ' ' * (max_author_name_len - len(author_name))

        items = [
            f"""{author_avatar}{author_name:<{max_author_name_len}}""",
            f""" {r['project_name'][0:10]:<10} """,
            f"""{age_days:>3}d"""
        ]

        link_title = f"""{r['title'][:60]:<60}"""
        if own_mr:
            link_title = green(link_title)
        items.append(f""" {link(r['web_url'], link_title):<70} """)

        flags = []
        has_problems = False
        if r['has_conflicts']:
            has_problems = True
            flags.append('🛑')
        if r['pipeline_status'] == 'failed':
            has_problems = True
            flags.append('💥')
        if r['pipeline_status'] == 'success' and not has_problems:
            flags.append('🚦')
        if not flags:
            flags.append('⏳')

        if r['unresolved_count']:
            flags.append(subscript(r['unresolved_count']) + '💬')

        w = 5
        if len(flags) > 1:
            w -= 1

        items.append(f"""{' '.join(flags):<{w}}""")

        if r['approvals']:
            trusted_approvals, approvals = [], []
            for a in r['approvals']:

                if a in r['eligible_approvers']:
                    trusted_approvals.append(green(a))
                else:
                    approvals.append(cyan(a))
            trusted_approvals, approvals = sorted(trusted_approvals), sorted(approvals)
            trusted_approvals.extend(approvals)

            items.append(f""" ✅ {', '.join(trusted_approvals)}""")

        else:
            items.append('')

        print('|'.join(items))


def log_error(wrapped, *args, **kwargs):
    def wrap():
        try:
            wrapped(*args, **kwargs)
        except RuntimeError as rt:
            print(f'error has occurred: {rt}', )
        except client_exceptions.ContentTypeError as ct:
            print(f'invalid response content-type at {ct.request_info.url} : {ct.message}', )

    return wrap


@log_error
def main():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(async_main())


if __name__ == '__main__':
    main()
