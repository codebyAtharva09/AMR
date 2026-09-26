# EdgeSwarm peer state: the only message robots exchange (one per robot per tick, ~300 bytes).
# Field-for-field mirror of the STATE payload in src/swarm/agent.py::_build_messages.
string robot_id
builtin_interfaces/Time stamp
int32 tick                      # sender's tick when sent (freshness check)
int32[2] pos                    # p   : current cell
int32[2] heading                # h
string state                    # s   : IDLE / TO_PICKUP / PICKING / ...
string task_id                  # task
bool carrying                   # c
int32[] priority                # pr  : rank tuple used by the safety rule
int32[] path_xy                 # path: flattened [x0,y0,x1,y1,...] reserved cells, in time order
int32[2] declared_next          # nx  : binding next-cell declaration (safety layer)
bool has_declared_next
string waiting_for              # wf
float32 battery                 # b
bool stationary                 # st
string comm_mode                # cm  : CONNECTED / DEGRADED / PREDICTIVE_LOCAL / SAFE_FALLBACK / RECOVERED
int32 task_priority             # tp
string claim_json               # claim: task-claim record (small JSON)
int32[] blocked_xy_first_seen   # blk : gossip of blocked aisles [x,y,tick,...]
int32[] cleared_xy_when         # clr
string yield_request_json       # yr
int32 tasks_done                # done_n
