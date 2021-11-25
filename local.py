#!/usr/local/bin/python3 -u
# -*- coding:utf-8 -*-

import sys, os

PRJ_ROOT = os.path.abspath(sys.path[0]) + os.path.sep
sys.path.append(PRJ_ROOT)
import json
import time
import traceback
import Utility as util
import socket
import queue


class Local:

    def __init__(self):
        self.conf = json.loads(open(PRJ_ROOT + '/conf_local.json').read())
        self.conf = self.conf['local']
        self.id = self.conf['id']
        self.AB_host = self.conf['host_addr']
        self.ctl_port = self.conf['ctl_port']
        self.B_port = self.conf['B_port']
        self.recv_size = self.conf['recv_size']
        self.queue_size = self.conf['queue_size']
        self.queue_timeout = self.conf['queue_timeout']
        self.recv_timeout = self.conf['recv_timeout']
        self.BD_map = {}
        self.DB_map = {}
        self.D_cons = {}
        self.B_cons = {}

        self.g_host_local = {}

    def execute(self):
        self.controller_run()

    def controller_run(self):
        s = None
        while True:
            try:
                if not s:
                    s = self.connect(self.AB_host, self.ctl_port)
                    id_info = {"id": self.id}
                    id_info = json.dumps(id_info)
                    s.send(bytes(str(id_info).encode('utf-8')))
                cmd = s.recv(self.recv_size)
                if not cmd:
                    util.log("ctl connection lost")
                    raise Exception('broken connection')
                cmd = cmd.decode('utf-8')
                util.simple_thread(target=self.execute_cmd, args=(cmd, s))
            except Exception as e:
                util.log(e)
                if e.args[0] == 'broken connection':
                    s = None



    def connect(self, host, port, retry=0, retry_inteval=1):
        n = 0
        while n < retry or not retry:
            n = n + 1
            try:
                s = socket.socket(socket.AF_INET)
                s.connect((host, int(port)))
                util.log("connect at host:{},port:{}".format(host, port))
                return s
            except Exception as e:
                util.log("connect : {}:{} try:{},err:{}".format(host, port, n, traceback.format_exc()))
                time.sleep(retry_inteval)
        return None

    def execute_cmd(self, cmd, s):
        try:
            if isinstance(cmd, str):
                cmd = json.loads(cmd)
            util.log('exc cmd:{}'.format(json.dumps(cmd)))
            if "type" in cmd and "d_host" in cmd and "d_port" in cmd and "s_host" in cmd and "s_port" in cmd:
                if cmd['type'] == 'open':
                    r = self.open(cmd['d_host'], cmd['d_port'])
                    if r:
                        back_msg = {
                            "c_port": r,
                            "s_host": cmd['s_host'],
                            "s_port": cmd['s_port'],
                        }
                        back_msg = json.dumps(back_msg)
                        s.send(bytes(str(back_msg).encode('utf-8')))
                        util.log('ctl send back:{}'.format(back_msg))
                else:
                    util.log('wrong type:{}'.format(cmd['type']))
            else:
                util.log('rev err cmd:{}'.format(json.dumps(cmd)))
        except Exception as e:
            util.log(traceback.format_exc())

    def open(self, D_host, D_port):
        # 连接D
        D_s = self.connect(D_host, D_port, retry=5)
        if not D_s:
            util.log('con to D fail:{}:{}'.format(D_host, D_port))
            return
        else:
            util.log('get con to D:{}:{}'.format(D_host, D_port))
        try:
            D_s.settimeout(self.recv_timeout)
            D_info = "{}_{}".format(D_host, str(D_port))
            self.D_cons[D_info] = D_s
        except Exception as e:
            util.log("get B info err:{}".format(e))
            return

        # 连接B
        B_s = self.connect(self.AB_host, self.B_port, retry=5)
        if not B_s:
            util.log('con to B fail:{}:{}'.format(self.AB_host, self.B_port))
            return
        else:
            util.log('get con to B:{}:{}'.format(self.AB_host, self.B_port))
        try:
            B_s.settimeout(self.recv_timeout)
            B_info = B_s.getpeername()
            B_host = B_info[0]
            B_port = B_info[1]
            B_info = "{}_{}".format(B_host, str(B_port))
            self.B_cons[B_info] = B_s
        except Exception as e:
            util.log("get B info err:{}".format(e))
            D_s.close()
            return

        self.BD_map[B_info] = D_info
        self.DB_map[D_info] = B_info
        B_q = queue.Queue(self.queue_size)
        D_q = queue.Queue(self.queue_size)
        util.simple_thread(target=self.B_recv, args=(B_s, B_info, B_q, D_s))
        util.simple_thread(target=self.B_send, args=(D_s, B_q))
        util.simple_thread(target=self.D_recv, args=(D_s, D_info, D_q, B_s))
        util.simple_thread(target=self.D_send, args=(B_s, D_q))
        C_port = B_s.getsockname()[1]
        return C_port

    def B_recv(self, s, B_info, q, D_s):
        while True:
            try:
                # 接收到B
                r = s.recv(self.recv_size)
                if not r:
                    raise Exception("B connect broken:{}".format(B_info))
                # 加入到队列
                q.put(r)
            except Exception as e:
                if isinstance(e,socket.timeout):
                    try:
                        # 判活
                        D_s.getsockname()
                        s.getsockname()
                    except Exception as e:
                        util.log(e)
                        break
                    continue
                else:
                    util.log("B rev err:{}".format(e))
                    break
        del q
        s.close()
        D_s.close()
        util.log("B recv thread exit")

    def B_send(self, D_s, q):
        while True:
            try:
                r = q.get(timeout=self.queue_timeout)
                # 转发给D
                D_s.send(r)
            except Exception as e:
                if isinstance(e,queue.Empty):
                    try:
                        # 判活
                        D_s.getsockname()
                    except Exception as e:
                        util.log(e)
                        break
                    continue
                else:
                    util.log("B send err:{}".format(e))
                    break
        D_s.close()
        util.log("B send thread exit")

    def D_recv(self, s, D_info, q, B_s):
        while True:
            try:
                # 接收到D
                r = s.recv(self.recv_size)
                if not r:
                    print(type(r),r)
                    raise Exception("D connect broken:{}".format(D_info))
                # 加入到队列
                q.put(r)
            except Exception as e:
                if isinstance(e, socket.timeout):
                    try:
                        # 判活
                        B_s.getsockname()
                        s.getsockname()
                    except Exception as e:
                        util.log(e)
                        break
                    continue
                else:
                    util.log("D rev err:{}".format(e))
                    break
        del q
        s.close()
        B_s.close()
        util.log("D recv thread exit")

    def D_send(self, B_s, q):
        while True:
            try:
                r = q.get(timeout=self.queue_timeout)
                # 转发给D
                B_s.send(r)
            except Exception as e:
                if isinstance(e,queue.Empty):
                    try:
                        # 判活
                        B_s.getsockname()
                    except Exception as e:
                        util.log(e)
                        break
                    continue
                else:
                    util.log("D send err:{}".format(e))
                    break
        B_s.close()
        util.log("D send thread exit")


if __name__ == '__main__':
    foo = Local()
    foo.execute()
