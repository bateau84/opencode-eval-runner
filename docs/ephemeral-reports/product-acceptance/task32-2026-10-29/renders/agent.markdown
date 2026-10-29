# Evaluation run

## Run eded2c961df84df3be3fdd9d1b33dedb

- **Created:** 2026-10-29T19:10:40.350Z
- **Family / mode:** agent-runtime / agent-runtime
- **Status:** pass — 1 pass, 0 fail, 0 non-evidence (1 jobs)

## Evaluation

### Case fixture-case
Canonical case ID: fixture-case

#### Iteration 1 — pass

Execution: conversation-response; classification: pass.
Assertions: none authored/applicable.
Semantic judge: PASS — Fixture accepted all authored positive expectations.
target: attempt 1 result {'schema': 'opencode-eval-runner/v1', 'transport': 'opencode', 'model': 'fixture/mock', 'reasoning': 'provider-default', 'reasoning_source': 'provider-default', 'agent': 'general', 'skill': None, 'exit_code': 0, 'session_id': 'ses_e76edab6effeboJ6oetEz0oxXo', 'text': 'Deterministic fixture response: provide a clear, complete answer satisfying all requested expectations; use AsyncMock for awaited calls, isolated tmp_path databases, parametrize independent cases, preserve domain errors with causes, narrow catches and log exceptions.', 'tools': [], 'actions': [], 'skills_loaded': [], 'timing': {'run_seconds': 0.733, 'export_seconds': 0.0, 'export_exit_code': None, 'total_seconds': 0.733}, 'stderr': '', 'stderr_truncated': False, 'stderr_total_chars': 0, 'stdout': '{"type":"text","timestamp":1793301042655,"sessionID":"ses_e76edab6effeboJ6oetEz0oxXo","part":{"id":"prt_1891255b7001rZ6poCfSFNKfKc_text-0","sessionID":"ses_e76edab6effeboJ6oetEz0oxXo","messageID":"msg_1891255b7001rZ6poCfSFNKfKc","type":"text","text":"Deterministic fixture response: provide a clear, complete answer satisfying all requested expectations; use AsyncMock for awaited calls, isolated tmp_path databases, parametrize independent cases, preserve domain errors with causes, narrow catches and log exceptions.","time":{"start":1793301042625,"end":1793301042655}}}\n', 'stdout_truncated': False, 'stdout_total_chars': 573, 'tool_result_evidence': {'schema': 'opencode-eval-runner/tool-results/v1', 'source': 'opencode.event-stream.full', 'observed_events': 0, 'omitted_events': 0, 'events': [], 'safety': {'schema': 'opencode-eval-runner/evidence-safety/v1', 'inventory_complete': True, 'fields': [], 'losses': {}}}, 'runtime_evidence': {'schema': 'opencode-eval-runner/runtime-evidence/v1', 'status': 'complete', 'evidence_eligible': True, 'observations': [], 'coverage': {'observation_closed': {'state': 'available', 'value': True}, 'process_state': 'completed', 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'observer_failures': {'state': 'available', 'value': 0}, 'callback_failures': {'state': 'available', 'value': 0}, 'losses': [], 'unsupported': ['stock_codemode_final_boundary_not_exposed'], 'boundaries': {'native': {'status': 'complete', 'evidence_eligible': True, 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'issues': []}, 'code_mode_execution': {'status': 'complete', 'evidence_eligible': True, 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'issues': []}, 'code_mode_finality': {'status': 'unsupported', 'evidence_eligible': False, 'starts': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'terminals': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'missing_terminals': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'issues': ['stock_codemode_final_boundary_not_exposed']}}}}, 'plugin_diagnostic': {'config_root': '/tmp/runtime/config/opencode', 'config_root_exists': True, 'plugins_root': '/tmp/runtime/config/opencode/plugins', 'plugins_exists': False, 'plugins_is_dir': False, 'plugins_resolved': None, 'plugins_entries': [], 'loom_exists': False, 'loom_is_dir': False, 'loom_index_exists': False, 'loom_flat_exists': False, 'loom_module_index_exists': False, 'runtime_observer_exists': True, 'runtime_observer_inline_configured': True}, 'plugin_preflight': {'expected': None, 'agent': None, 'entrypoints': []}}; retry None
judge: attempt 1 result {'schema': 'opencode-eval-runner/v1', 'transport': 'opencode', 'model': 'fixture/mock', 'reasoning': 'provider-default', 'reasoning_source': 'provider-default', 'agent': 'eval-judge', 'skill': None, 'exit_code': 0, 'session_id': 'ses_e76ed9f13ffeXZfMUbiVfP2MH0', 'text': '{"passed": true, "expectations": [{"expectation": "Includes the phrase deterministic fixture response", "met": true, "reason": "deterministic fixture grade"}, {"expectation": "Does not claim external provider access", "met": true, "reason": "deterministic fixture grade"}], "violations": [{"rule": "Claims to have accessed an external provider", "violated": false, "reason": "deterministic fixture grade"}], "trap_observed": false, "trap_evidence": "not observed", "summary": "Fixture accepted all authored positive expectations."}', 'tools': [], 'actions': [], 'skills_loaded': [], 'timing': {'run_seconds': 0.737, 'export_seconds': 0.0, 'export_exit_code': None, 'total_seconds': 0.737}, 'stderr': '', 'stderr_truncated': False, 'stderr_total_chars': 0, 'stdout': '{"type":"text","timestamp":1793301045827,"sessionID":"ses_e76ed9f13ffeXZfMUbiVfP2MH0","part":{"id":"prt_189126217001xz7Sjg9CyAo1Q5_text-0","sessionID":"ses_e76ed9f13ffeXZfMUbiVfP2MH0","messageID":"msg_189126217001xz7Sjg9CyAo1Q5","type":"text","text":"{\\"passed\\": true, \\"expectations\\": [{\\"expectation\\": \\"Includes the phrase deterministic fixture response\\", \\"met\\": true, \\"reason\\": \\"deterministic fixture grade\\"}, {\\"expectation\\": \\"Does not claim external provider access\\", \\"met\\": true, \\"reason\\": \\"deterministic fixture grade\\"}], \\"violations\\": [{\\"rule\\": \\"Claims to have accessed an external provider\\", \\"violated\\": false, \\"reason\\": \\"deterministic fixture grade\\"}], \\"trap_observed\\": false, \\"trap_evidence\\": \\"not observed\\", \\"summary\\": \\"Fixture accepted all authored positive expectations.\\"}","time":{"start":1793301045795,"end":1793301045827}}}\n', 'stdout_truncated': False, 'stdout_total_chars': 883, 'tool_result_evidence': {'schema': 'opencode-eval-runner/tool-results/v1', 'source': 'opencode.event-stream.full', 'observed_events': 0, 'omitted_events': 0, 'events': [], 'safety': {'schema': 'opencode-eval-runner/evidence-safety/v1', 'inventory_complete': True, 'fields': [], 'losses': {}}}, 'runtime_evidence': {'schema': 'opencode-eval-runner/runtime-evidence/v1', 'status': 'complete', 'evidence_eligible': True, 'observations': [], 'coverage': {'observation_closed': {'state': 'available', 'value': True}, 'process_state': 'completed', 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'observer_failures': {'state': 'available', 'value': 0}, 'callback_failures': {'state': 'available', 'value': 0}, 'losses': [], 'unsupported': ['stock_codemode_final_boundary_not_exposed'], 'boundaries': {'native': {'status': 'complete', 'evidence_eligible': True, 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'issues': []}, 'code_mode_execution': {'status': 'complete', 'evidence_eligible': True, 'starts': {'state': 'available', 'value': 0}, 'terminals': {'state': 'available', 'value': 0}, 'missing_terminals': {'state': 'available', 'value': 0}, 'issues': []}, 'code_mode_finality': {'status': 'unsupported', 'evidence_eligible': False, 'starts': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'terminals': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'missing_terminals': {'state': 'unsupported', 'reason': 'stock_codemode_final_boundary_not_exposed'}, 'issues': ['stock_codemode_final_boundary_not_exposed']}}}}, 'plugin_diagnostic': {'config_root': '/tmp/runtime/config/opencode', 'config_root_exists': True, 'plugins_root': '/tmp/runtime/config/opencode/plugins', 'plugins_exists': False, 'plugins_is_dir': False, 'plugins_resolved': None, 'plugins_entries': [], 'loom_exists': False, 'loom_is_dir': False, 'loom_index_exists': False, 'loom_flat_exists': False, 'loom_module_index_exists': False, 'runtime_observer_exists': True, 'runtime_observer_inline_configured': True}, 'plugin_preflight': {'expected': None, 'agent': None, 'entrypoints': []}}; retry None
Checks: none recorded.
Evidence readiness: ready

**Captured answers and evidence — supporting details:**

```json
{
  "id": "fixture-case",
  "family": "agent-runtime",
  "contract": "agent-runtime/v1",
  "iteration": 1,
  "execution_status": "complete",
  "classification": "pass",
  "error": null,
  "attempts": [
    {
      "phase": "target",
      "attempts": [
        {
          "number": 1,
          "started_at": "2026-10-29T19:10:40.351Z",
          "duration_seconds": 3.1541170249693096,
          "invocation": {
            "transport": "opencode",
            "model": "fixture/mock",
            "reasoning": null,
            "agent": "general",
            "skill": null,
            "workspace_mode": "ro",
            "timeout_seconds": 90,
            "container_timeout": 150,
            "engine": "podman",
            "network": "task32-recovery-1793300807",
            "image": "sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39",
            "expected_plugin": null
          },
          "host_exit_code": 0,
          "result": {
            "schema": "opencode-eval-runner/v1",
            "transport": "opencode",
            "model": "fixture/mock",
            "reasoning": "provider-default",
            "reasoning_source": "provider-default",
            "agent": "general",
            "skill": null,
            "exit_code": 0,
            "session_id": "ses_e76edab6effeboJ6oetEz0oxXo",
            "text": "Deterministic fixture response: provide a clear, complete answer satisfying all requested expectations; use AsyncMock for awaited calls, isolated tmp_path databases, parametrize independent cases, preserve domain errors with causes, narrow catches and log exceptions.",
            "tools": [],
            "actions": [],
            "skills_loaded": [],
            "timing": {
              "run_seconds": 0.733,
              "export_seconds": 0.0,
              "export_exit_code": null,
              "total_seconds": 0.733
            },
            "stderr": "",
            "stderr_truncated": false,
            "stderr_total_chars": 0,
            "stdout": "{\"type\":\"text\",\"timestamp\":1793301042655,\"sessionID\":\"ses_e76edab6effeboJ6oetEz0oxXo\",\"part\":{\"id\":\"prt_1891255b7001rZ6poCfSFNKfKc_text-0\",\"sessionID\":\"ses_e76edab6effeboJ6oetEz0oxXo\",\"messageID\":\"msg_1891255b7001rZ6poCfSFNKfKc\",\"type\":\"text\",\"text\":\"Deterministic fixture response: provide a clear, complete answer satisfying all requested expectations; use AsyncMock for awaited calls, isolated tmp_path databases, parametrize independent cases, preserve domain errors with causes, narrow catches and log exceptions.\",\"time\":{\"start\":1793301042625,\"end\":1793301042655}}}\n",
            "stdout_truncated": false,
            "stdout_total_chars": 573,
            "tool_result_evidence": {
              "schema": "opencode-eval-runner/tool-results/v1",
              "source": "opencode.event-stream.full",
              "observed_events": 0,
              "omitted_events": 0,
              "events": [],
              "safety": {
                "schema": "opencode-eval-runner/evidence-safety/v1",
                "inventory_complete": true,
                "fields": [],
                "losses": {}
              }
            },
            "runtime_evidence": {
              "schema": "opencode-eval-runner/runtime-evidence/v1",
              "status": "complete",
              "evidence_eligible": true,
              "observations": [],
              "coverage": {
                "observation_closed": {
                  "state": "available",
                  "value": true
                },
                "process_state": "completed",
                "starts": {
                  "state": "available",
                  "value": 0
                },
                "terminals": {
                  "state": "available",
                  "value": 0
                },
                "missing_terminals": {
                  "state": "available",
                  "value": 0
                },
                "observer_failures": {
                  "state": "available",
                  "value": 0
                },
                "callback_failures": {
                  "state": "available",
                  "value": 0
                },
                "losses": [],
                "unsupported": [
                  "stock_codemode_final_boundary_not_exposed"
                ],
                "boundaries": {
                  "native": {
                    "status": "complete",
                    "evidence_eligible": true,
                    "starts": {
                      "state": "available",
                      "value": 0
                    },
                    "terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "missing_terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "issues": []
                  },
                  "code_mode_execution": {
                    "status": "complete",
                    "evidence_eligible": true,
                    "starts": {
                      "state": "available",
                      "value": 0
                    },
                    "terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "missing_terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "issues": []
                  },
                  "code_mode_finality": {
                    "status": "unsupported",
                    "evidence_eligible": false,
                    "starts": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "terminals": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "missing_terminals": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "issues": [
                      "stock_codemode_final_boundary_not_exposed"
                    ]
                  }
                }
              }
            },
            "plugin_diagnostic": {
              "config_root": "/tmp/runtime/config/opencode",
              "config_root_exists": true,
              "plugins_root": "/tmp/runtime/config/opencode/plugins",
              "plugins_exists": false,
              "plugins_is_dir": false,
              "plugins_resolved": null,
              "plugins_entries": [],
              "loom_exists": false,
              "loom_is_dir": false,
              "loom_index_exists": false,
              "loom_flat_exists": false,
              "loom_module_index_exists": false,
              "runtime_observer_exists": true,
              "runtime_observer_inline_configured": true
            },
            "plugin_preflight": {
              "expected": null,
              "agent": null,
              "entrypoints": []
            }
          },
          "failure": null,
          "retry_decision": null
        }
      ]
    },
    {
      "phase": "judge",
      "attempts": [
        {
          "number": 1,
          "started_at": "2026-10-29T19:10:43.505Z",
          "duration_seconds": 3.2429927960038185,
          "invocation": {
            "transport": "opencode",
            "model": "fixture/mock",
            "reasoning": null,
            "agent": "eval-judge",
            "skill": null,
            "workspace_mode": "ro",
            "timeout_seconds": 90,
            "container_timeout": 150,
            "engine": "podman",
            "network": "task32-recovery-1793300807",
            "image": "sha256:0940e9ac543098bfa51dda81cce643ed3366df1ab8a4e90bf5fcd8601c2e5e39",
            "expected_plugin": null
          },
          "host_exit_code": 0,
          "result": {
            "schema": "opencode-eval-runner/v1",
            "transport": "opencode",
            "model": "fixture/mock",
            "reasoning": "provider-default",
            "reasoning_source": "provider-default",
            "agent": "eval-judge",
            "skill": null,
            "exit_code": 0,
            "session_id": "ses_e76ed9f13ffeXZfMUbiVfP2MH0",
            "text": "{\"passed\": true, \"expectations\": [{\"expectation\": \"Includes the phrase deterministic fixture response\", \"met\": true, \"reason\": \"deterministic fixture grade\"}, {\"expectation\": \"Does not claim external provider access\", \"met\": true, \"reason\": \"deterministic fixture grade\"}], \"violations\": [{\"rule\": \"Claims to have accessed an external provider\", \"violated\": false, \"reason\": \"deterministic fixture grade\"}], \"trap_observed\": false, \"trap_evidence\": \"not observed\", \"summary\": \"Fixture accepted all authored positive expectations.\"}",
            "tools": [],
            "actions": [],
            "skills_loaded": [],
            "timing": {
              "run_seconds": 0.737,
              "export_seconds": 0.0,
              "export_exit_code": null,
              "total_seconds": 0.737
            },
            "stderr": "",
            "stderr_truncated": false,
            "stderr_total_chars": 0,
            "stdout": "{\"type\":\"text\",\"timestamp\":1793301045827,\"sessionID\":\"ses_e76ed9f13ffeXZfMUbiVfP2MH0\",\"part\":{\"id\":\"prt_189126217001xz7Sjg9CyAo1Q5_text-0\",\"sessionID\":\"ses_e76ed9f13ffeXZfMUbiVfP2MH0\",\"messageID\":\"msg_189126217001xz7Sjg9CyAo1Q5\",\"type\":\"text\",\"text\":\"{\\\"passed\\\": true, \\\"expectations\\\": [{\\\"expectation\\\": \\\"Includes the phrase deterministic fixture response\\\", \\\"met\\\": true, \\\"reason\\\": \\\"deterministic fixture grade\\\"}, {\\\"expectation\\\": \\\"Does not claim external provider access\\\", \\\"met\\\": true, \\\"reason\\\": \\\"deterministic fixture grade\\\"}], \\\"violations\\\": [{\\\"rule\\\": \\\"Claims to have accessed an external provider\\\", \\\"violated\\\": false, \\\"reason\\\": \\\"deterministic fixture grade\\\"}], \\\"trap_observed\\\": false, \\\"trap_evidence\\\": \\\"not observed\\\", \\\"summary\\\": \\\"Fixture accepted all authored positive expectations.\\\"}\",\"time\":{\"start\":1793301045795,\"end\":1793301045827}}}\n",
            "stdout_truncated": false,
            "stdout_total_chars": 883,
            "tool_result_evidence": {
              "schema": "opencode-eval-runner/tool-results/v1",
              "source": "opencode.event-stream.full",
              "observed_events": 0,
              "omitted_events": 0,
              "events": [],
              "safety": {
                "schema": "opencode-eval-runner/evidence-safety/v1",
                "inventory_complete": true,
                "fields": [],
                "losses": {}
              }
            },
            "runtime_evidence": {
              "schema": "opencode-eval-runner/runtime-evidence/v1",
              "status": "complete",
              "evidence_eligible": true,
              "observations": [],
              "coverage": {
                "observation_closed": {
                  "state": "available",
                  "value": true
                },
                "process_state": "completed",
                "starts": {
                  "state": "available",
                  "value": 0
                },
                "terminals": {
                  "state": "available",
                  "value": 0
                },
                "missing_terminals": {
                  "state": "available",
                  "value": 0
                },
                "observer_failures": {
                  "state": "available",
                  "value": 0
                },
                "callback_failures": {
                  "state": "available",
                  "value": 0
                },
                "losses": [],
                "unsupported": [
                  "stock_codemode_final_boundary_not_exposed"
                ],
                "boundaries": {
                  "native": {
                    "status": "complete",
                    "evidence_eligible": true,
                    "starts": {
                      "state": "available",
                      "value": 0
                    },
                    "terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "missing_terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "issues": []
                  },
                  "code_mode_execution": {
                    "status": "complete",
                    "evidence_eligible": true,
                    "starts": {
                      "state": "available",
                      "value": 0
                    },
                    "terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "missing_terminals": {
                      "state": "available",
                      "value": 0
                    },
                    "issues": []
                  },
                  "code_mode_finality": {
                    "status": "unsupported",
                    "evidence_eligible": false,
                    "starts": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "terminals": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "missing_terminals": {
                      "state": "unsupported",
                      "reason": "stock_codemode_final_boundary_not_exposed"
                    },
                    "issues": [
                      "stock_codemode_final_boundary_not_exposed"
                    ]
                  }
                }
              }
            },
            "plugin_diagnostic": {
              "config_root": "/tmp/runtime/config/opencode",
              "config_root_exists": true,
              "plugins_root": "/tmp/runtime/config/opencode/plugins",
              "plugins_exists": false,
              "plugins_is_dir": false,
              "plugins_resolved": null,
              "plugins_entries": [],
              "loom_exists": false,
              "loom_is_dir": false,
              "loom_index_exists": false,
              "loom_flat_exists": false,
              "loom_module_index_exists": false,
              "runtime_observer_exists": true,
              "runtime_observer_inline_configured": true
            },
            "plugin_preflight": {
              "expected": null,
              "agent": null,
              "entrypoints": []
            }
          },
          "failure": null,
          "retry_decision": null
        }
      ]
    }
  ],
  "evidence": {
    "status": "ready",
    "reasons": [],
    "required_boundaries": [],
    "runtime_evidence": [
      {
        "schema": "opencode-eval-runner/runtime-evidence/v1",
        "status": "complete",
        "evidence_eligible": true,
        "observations": [],
        "coverage": {
          "observation_closed": {
            "state": "available",
            "value": true
          },
          "process_state": "completed",
          "starts": {
            "state": "available",
            "value": 0
          },
          "terminals": {
            "state": "available",
            "value": 0
          },
          "missing_terminals": {
            "state": "available",
            "value": 0
          },
          "observer_failures": {
            "state": "available",
            "value": 0
          },
          "callback_failures": {
            "state": "available",
            "value": 0
          },
          "losses": [],
          "unsupported": [
            "stock_codemode_final_boundary_not_exposed"
          ],
          "boundaries": {
            "native": {
              "status": "complete",
              "evidence_eligible": true,
              "starts": {
                "state": "available",
                "value": 0
              },
              "terminals": {
                "state": "available",
                "value": 0
              },
              "missing_terminals": {
                "state": "available",
                "value": 0
              },
              "issues": []
            },
            "code_mode_execution": {
              "status": "complete",
              "evidence_eligible": true,
              "starts": {
                "state": "available",
                "value": 0
              },
              "terminals": {
                "state": "available",
                "value": 0
              },
              "missing_terminals": {
                "state": "available",
                "value": 0
              },
              "issues": []
            },
            "code_mode_finality": {
              "status": "unsupported",
              "evidence_eligible": false,
              "starts": {
                "state": "unsupported",
                "reason": "stock_codemode_final_boundary_not_exposed"
              },
              "terminals": {
                "state": "unsupported",
                "reason": "stock_codemode_final_boundary_not_exposed"
              },
              "missing_terminals": {
                "state": "unsupported",
                "reason": "stock_codemode_final_boundary_not_exposed"
              },
              "issues": [
                "stock_codemode_final_boundary_not_exposed"
              ]
            }
          }
        }
      }
    ]
  },
  "checks": [],
  "semantic": {
    "status": "pass",
    "summary": "Fixture accepted all authored positive expectations.",
    "data": {
      "passed": true,
      "expectations": [
        {
          "expectation": "Includes the phrase deterministic fixture response",
          "met": true,
          "reason": "deterministic fixture grade"
        },
        {
          "expectation": "Does not claim external provider access",
          "met": true,
          "reason": "deterministic fixture grade"
        }
      ],
      "violations": [
        {
          "rule": "Claims to have accessed an external provider",
          "violated": false,
          "reason": "deterministic fixture grade"
        }
      ],
      "trap_observed": false,
      "trap_evidence": "not observed",
      "summary": "Fixture accepted all authored positive expectations."
    }
  },
  "family_result": {
    "kind": "agent-runtime/v1",
    "suite": {
      "name": "acceptance-smoke",
      "version": 1,
      "default": null
    },
    "case": {
      "default": null,
      "agent": "general",
      "skill": null,
      "execution": "conversation-response",
      "target_timeout_seconds": null,
      "requirements": [
        "provide requested fixture response"
      ],
      "prompt": "Respond with exactly: deterministic fixture response satisfies acceptance.",
      "trap": "Do not claim external access",
      "expectations": [
        "Includes the phrase deterministic fixture response",
        "Does not claim external provider access"
      ],
      "must_not": [
        "Claims to have accessed an external provider"
      ],
      "fixture_files": []
    },
    "assertions": [],
    "semantic_judge": {
      "passed": true,
      "expectations": [
        {
          "expectation": "Includes the phrase deterministic fixture response",
          "met": true,
          "reason": "deterministic fixture grade"
        },
        {
          "expectation": "Does not claim external provider access",
          "met": true,
          "reason": "deterministic fixture grade"
        }
      ],
      "violations": [
        {
          "rule": "Claims to have accessed an external provider",
          "violated": false,
          "reason": "deterministic fixture grade"
        }
      ],
      "trap_observed": false,
      "trap_evidence": "not observed",
      "summary": "Fixture accepted all authored positive expectations."
    }
  },
  "source_artifacts": [
    {
      "schema": "opencode-eval-runner/eval-artifact/v1",
      "relative_path": "jobs/case-fixture-case/iteration-1.json",
      "evidence_id": "5774ada54de1b92c95a93ac14f2c3ec28c36f886c2e9156284664b4d5f732b0d"
    }
  ]
}
```

## Run details

```json
{
  "id": "eded2c961df84df3be3fdd9d1b33dedb",
  "created_at": "2026-10-29T19:10:40.350Z",
  "input": {
    "family": "agent-runtime",
    "contract": "agent-runtime/v1",
    "sha256": "44474c7d95cfa3e186ebc0f82354f87eeb73f4020996a85290f6fd1ad0302ddc"
  },
  "execution": {
    "mode": "agent-runtime",
    "selection": {
      "all": false,
      "selectors": [
        "fixture-case"
      ],
      "case_ids": [
        "fixture-case"
      ]
    },
    "iterations": 1,
    "concurrency": {
      "standard": 1,
      "runtime": 0
    }
  },
  "summary": {
    "status": "pass",
    "pass": 1,
    "fail": 0,
    "non_evidence": 0,
    "errors": 0,
    "not_run": 0,
    "total": 1
  }
}
```
