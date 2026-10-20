"""Audit observed signal transitions, including a simulator-native baseline."""


class SignalAudit:
    def __init__(self,bindings,min_green=10,max_green=60,yellow=3,all_red=2):
        self.bindings=bindings
        self.min_green=min_green;self.max_green=max_green
        self.yellow=yellow;self.all_red=all_red
        self.current={};self.history=[]

    def observe(self,time,states):
        for node,state in states.items():
            binding=self.bindings[node]
            valid=binding['green']+binding['yellow']+[binding['red']]
            if state not in valid:
                raise RuntimeError('Unexpected or conflicting signal state at '+node)
            if node not in self.current:
                self.current[node]=(state,time)
                continue
            previous,start=self.current[node]
            if state==previous:
                if state in binding['green'] and time-start>self.max_green:
                    raise RuntimeError('Maximum green exceeded')
                continue
            duration=time-start
            if previous in binding['green']:
                phase=binding['green'].index(previous)
                if state!=binding['yellow'][phase] or not self.min_green<=duration<=self.max_green:
                    raise RuntimeError('Green duration or yellow transition violated')
            elif previous in binding['yellow']:
                if state!=binding['red'] or duration!=self.yellow:
                    raise RuntimeError('Yellow duration or all-red transition violated')
            else:
                if state not in binding['green'] or duration!=self.all_red:
                    raise RuntimeError('All-red clearance violated')
            self.history.append({'node':node,'start':start,'end':time,'state':previous,'duration':duration})
            self.current[node]=(state,time)

    def metrics(self,time):
        green=[row['duration'] for row in self.history if row['state'] in self.bindings[row['node']]['green']]
        active=[time-start for node,(state,start) in self.current.items() if state in self.bindings[node]['green']]
        return {'phase_changes':len(green),'minimum_green_before_switch_seconds':min(green) if green else None,
                'maximum_green_observed_seconds':max(green+active,default=0),'signal_audit_violations':0}
