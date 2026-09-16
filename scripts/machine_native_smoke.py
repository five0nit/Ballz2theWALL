"""Scratch-native parsing/discovery only; never invoke models or grant OS rights."""
import argparse
import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager


@contextmanager
def scratch_controller(root):
    """Public activation/OFF against an empty home; runtime discovery alone is injected."""
    from unittest.mock import patch

    from ballz2thewall.onboarding import Activation
    state = root / 'state'
    home = root / 'controller-agent'
    home.mkdir()
    controller = Activation(state)
    with patch('ballz2thewall.onboarding.require_runtime', return_value={'executable': 'scratch fixture only'}):
        record = controller.enable('hermes', home, machine_access=True)
    try:
        yield state, record
    finally:
        assert controller.disable()['phase'] == 'off'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path, help="Path for the JSON verification receipt")
    options = parser.parse_args()

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import ballz2thewall
    from ballz2thewall.adapters import get_adapter
    from ballz2thewall.config import make_plan
    from ballz2thewall.machine import server_spec
    from ballz2thewall.machine_bindings import augment_plan
    from ballz2thewall.openclaw import make_plans

    assert 'site-packages' in pathlib.Path(ballz2thewall.__file__).parts
    output = {'version': ballz2thewall.__version__, 'package': ballz2thewall.__file__, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='ballz-native-') as tmp, scratch_controller(pathlib.Path(tmp)) as (state, record):
        root = pathlib.Path(tmp)
        async def probe():
            spec = server_spec(state, record['id'])
            spec['env'] = {'HOME': str(root), 'USERPROFILE': str(root), 'XDG_STATE_HOME': str(root/'xdg-state'),
                           'XDG_CONFIG_HOME': str(root/'xdg-config'), 'XDG_CACHE_HOME': str(root/'xdg-cache')}
            async with stdio_client(StdioServerParameters(**spec)) as transport:
                async with ClientSession(*transport) as session:
                    await session.initialize()
                    names = sorted(t.name for t in (await session.list_tools()).tools)
                    assert {'machine_exec', 'machine_file', 'machine_status'}.issubset(names)
                    assert any(n.startswith('desktop_') for n in names)
                    status = await session.call_tool('machine_status', {})
                    assert not status.isError
                    result = await session.call_tool('machine_exec', {'argv': [sys.executable, '-I', '-c', 'print("NATIVE_MCP_OK")'], 'cwd': str(root)})
                    assert not result.isError
                    assert json.loads(result.content[0].text)['stdout'].strip() == 'NATIVE_MCP_OK'
                    output['checks'].append({'name':'real_mcp_with_native_driver','pass':True,'tool_count':len(names), 'tool_names':names})
        asyncio.run(asyncio.wait_for(probe(), 65))
        env = {k:v for k,v in os.environ.items() if k in {'PATH','SystemRoot','WINDIR','LANG','LC_ALL','TMP','TEMP','COMSPEC'}}
        env.update(HOME=str(root), USERPROFILE=str(root), HERMES_HOME=str(root/'hermes'), CODEX_HOME=str(root/'codex'),
                   CLAUDE_CONFIG_DIR=str(root/'claude'), OPENCLAW_STATE_DIR=str(root/'openclaw'),
                   OPENCLAW_CONFIG_PATH=str(root/'openclaw'/'openclaw.json'))
        commands = {
            'codex': [['mcp','get','ballz2thewall_machine','--json']],
            'hermes': [['mcp','test','ballz2thewall_machine']],
            'openclaw': [['config','validate','--json'], ['mcp','show','ballz2thewall_machine','--json'],
                         ['mcp','probe','ballz2thewall_machine','--json']],
        }
        for name in commands:
            executable = shutil.which(name)
            if not executable:
                output['checks'].append({'name':name,'pass':None,'reason':'native CLI unavailable'})
                continue
            home = root/name
            home.mkdir()
            plans = make_plans(home) if name == 'openclaw' else [make_plan(get_adapter(name), home)]
            plans[0] = augment_plan(plans[0], state, record['id'])
            for plan in plans:
                plan.target.write_bytes(plan.after)
            for args in commands[name]:
                result = subprocess.run([executable,*args],cwd=root,env=env,capture_output=True,text=True,timeout=90)
                output['checks'].append({'name':name+' '+' '.join(args), 'pass':result.returncode==0,
                                         'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr[-1500:]})
    output['checks'].append({'name': 'public_activation_off', 'pass': True,
                             'scope': 'scratch profile; runtime detection fixture, no model or OS approval'})
    options.output.write_text(json.dumps(output,indent=2), encoding="utf-8")
    print(json.dumps(output,indent=2))
    assert all(c['pass'] is not False for c in output['checks'])


if __name__ == "__main__":
    main()
