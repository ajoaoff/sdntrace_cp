"""Automate circuit traces."""

import time
import requests
from pyof.v0x01.common.phy_port import Port as Port10
from pyof.v0x04.common.port import PortNo as Port13
from napps.amlight.sdntrace_cp.utils import format_result, clean_circuits
from napps.amlight.sdntrace_cp import settings
from kytos.core import log


class Automate:
    """Find all circuits and automate trace execution."""

    def __init__(self, tracer):
        self._tracer = tracer
        self._circuits = []
        self.find_circuits()

    def find_circuits(self):
        """Discover all circuits in a topology.

        Using the list of flows per switch, run control plane
        traces to find a list of circuits."""
        all_flows = {}
        circuits = []

        for switch in self._tracer.controller.switches.values():
            all_flows[switch] = []
            if switch.ofp_version == '0x01':
                controller_port = Port10.OFPP_CONTROLLER
            else:
                controller_port = Port13.OFPP_CONTROLLER

            try:
                for flow in switch.generic_flows:
                    action_ok = False
                    in_port_ok = False
                    if 'in_port' in flow.match and flow.match['in_port'] != 0:
                        in_port_ok = True
                    if in_port_ok:
                        for action in flow.actions:
                            if action.action_type == 'output' \
                                    and action.port != controller_port:
                                action_ok = True
                    if action_ok:
                        all_flows[switch].append(flow)
            except AttributeError:
                pass

        for switch, flows in all_flows.items():
            for flow in flows:
                in_port = flow.match['in_port']
                vlan = flow.match['vlan_vid']
                if switch.ofp_version == '0x04':
                    in_port = in_port.value
                    vlan = vlan.value
                entries = {
                    'trace': {
                        'switch': {
                            'dpid': switch.dpid,
                            'in_port': in_port
                        },
                        'eth': {
                            'dl_vlan': vlan
                        }
                    }
                }
                result = self._tracer.tracepath(entries)
                circuits.append({'circuit': format_result(result),
                                 'entries': entries})

        self._circuits = clean_circuits(circuits, self._tracer.controller)

    def run_traces(self):
        """Run traces for all circuits."""

        results = []
        for circuit in self._circuits:
            entries = circuit['entries']
            result = self._tracer.tracepath(entries)
            try:
                result = format_result(result)
                if result != circuit['circuit']:
                    results.append(circuit)
            except KeyError:
                results.append(circuit)
        log.info('Results %s, tamanho %s' % (results, len(self._circuits)))
        return results

    def check_trace(self, trace):
        pass

    def run_important_traces(self):
        try:
            important_circuits = settings.IMPORTANT_CIRCUITS
        except AttributeError:
            return

        for circuit in important_circuits:
            entries = {
                'trace': {
                    'switch': {
                        'dpid': circuit['dpid_a'],
                        'in_port': circuit['port_a']
                    },
                    'eth': {
                        'dl_vlan': circuit['vlan_a']
                    }
                }
            }
            result = requests.put('http://localhost:8181/api/amlight/sdntrace/trace', json=entries)
            trace = result.json()
            trace_id = trace['result']['trace_id']
            type = None
            while type != 'last':
                time.sleep(5)
                result = requests.get('http://localhost:8181/api/amlight/sdntrace/trace/%s' % trace_id)
                trace = result.json()
                type = trace['result'][-1]['type']
            log.info(trace)
