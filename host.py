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


# graph: S-> [A->B]-> [C->D]

class Host:

    def __init__(self):
        self.conf = json.loads(open(PRJ_ROOT + '/conf_host.json').read())
        self.conf = self.conf['host']

        self.local = self.conf['bind_addr']

        # 下发指令给Local的端口;
        self.ctl_port = self.conf['ctl_port']
        # 与C端通信的端口
        self.B_port = self.conf['B_port']

        # S:host_port,C_id,D_ip,D_port
        self.port_map = self.conf['port_map']

        self.recv_size = self.conf['recv_size']
        self.queue_size = self.conf['queue_size']
        self.queue_timeout = self.conf['queue_timeout']
        self.recv_timeout = self.conf['recv_timeout']

        self.ctl_s = None
        self.CS_map = {}
        self.SC_map = {}
        self.ctl_cons = {}
        self.ctl_id_host_map = {}
        self.B_cons = {}
        self.B_q = {}
        self.S_cons = {}
        self.S_q = {}

    def execute(self):
        ctl_s = self.ctl_init()
        B_s = self.B_port_init()
        if not ctl_s or not B_s:
            return
        # 初始化cmd,等待连接
        util.simple_thread(target=self.ctl_accept, args=(ctl_s,))
        # 初始化B,等待连接
        util.simple_thread(target=self.B_accept, args=(B_s,))
        # 配置初始化
        self.init_srv()
        while True:
            time.sleep(1)

    def ctl_init(self):
        """初始化cmd服务"""
        s = self.bind(port=self.ctl_port)
        if s:
            s.listen()
            return s
        else:
            util.log('ctl init fail')
            return None

    def B_port_init(self):
        """初始化B服务"""
        s = self.bind(port=self.B_port)
        if s:
            s.listen()
            return s
        else:
            util.log('B port init fail')
            return None

    def ctl_accept(self, s):
        """cmd连接"""
        while True:
            try:
                a, _ = s.accept()
                a.settimeout(self.recv_timeout)
                C_host = a.getpeername()[0]
                self.ctl_cons[C_host] = a
                util.log("get ctl con:{}".format(str(a.getpeername()[1])))
                util.simple_thread(target=self.ctl_recv, args=(a, C_host))
            except Exception as e:
                traceback.print_exc()
                util.log('ctl accept err:{}'.format(e))

    def init_srv(self):
        """按配置初始化A端"""
        util.log("port_map:{}".format(json.dumps(self.port_map)))
        for A_port in self.port_map:
            try:
                s = self.bind(port=A_port, retry=3)
                if s:
                    s.listen()
                    util.simple_thread(target=self.A_accept, args=(s,))
            except Exception as e:
                util.log('get A_port:{} listen fail:{}'.format(A_port, e))
                continue

    def bind(self, port, retry=0, retry_inteval=1, reuse=True):
        s = socket.socket(socket.AF_INET)
        # 是否复用
        if reuse:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        n = 0
        while n < retry or not retry:
            n = n + 1
            try:
                s.bind((self.local, int(port)))
            except Exception as e:
                util.log("A_port bind try:{},err:{}".format(n, traceback.format_exc()))
                time.sleep(retry_inteval)
            return s
        util.log("bind port :{} fail".format(port))
        return None

    def cmd_send(self, C_host_id, cmd):
        """发送cmd"""
        if C_host_id not in self.ctl_id_host_map:
            util.log("send cmd to an no-connection client")
            return
        C_host = self.ctl_id_host_map[C_host_id]
        s = self.ctl_cons[C_host]
        try:
            if not isinstance(cmd, str):
                cmd = json.dumps(cmd)
            s.send(bytes(str(cmd).encode('utf-8')))
            util.log("send cmd to client:{} done,cmd:{}".format(C_host, cmd))
        except Exception as e:
            util.log("send cmd err:{}".format(e))
        return False

    def ctl_recv(self, s, C_host):
        """cmd接收处理"""
        while True:
            try:
                r = s.recv(self.recv_size)
                if not r:
                    util.log("ctl connect broken:{}".format(C_host))
                    del self.ctl_cons[C_host]
                    return
                r = r.decode('utf-8')
                util.log("ctl rev:" + r)
                r = json.loads(r)

                if "id" in r:
                    self.ctl_id_host_map[r['id']] = C_host
                    util.log("get ctl id msg:{}".format(r['id']))

                if "c_port" in r and "s_host" in r and "s_port" in r:
                    C_port = r['c_port']
                    S_host = r['s_host']
                    S_port = r['s_port']
                    S_info = "{}_{}".format(S_host, str(S_port))
                    C_info = "{}_{}".format(C_host, str(C_port))
                    self.SC_map[S_info] = C_info
                    self.CS_map[C_info] = S_info
                else:
                    util.log("bad ctl back msg:{}".format(r))
            except Exception as e:
                if isinstance(e,socket.timeout):
                    try:
                        # 判活
                        s.getsockname()
                    except:
                        s.close()
                        break
                    continue
                else:
                    util.log("ctl rev err:{}".format(e))
                    break
        del self.ctl_cons[C_host]

    def B_accept(self, s):
        """B连接"""
        while True:
            try:
                a, _ = s.accept()
                a.settimeout(self.recv_timeout)
                C_info = a.getpeername()
                C_host = C_info[0]
                C_port = C_info[1]
                C_info = "{}_{}".format(C_host, str(C_port))
                q = queue.Queue(self.queue_size)
                self.B_cons[C_info] = a
                self.B_q[C_info] = q

                util.log("B get C conn:{}".format(C_info))
                util.simple_thread(target=self.B_recv, args=(a, C_info, q))
                util.simple_thread(target=self.B_send, args=(C_info,))
            except Exception as e:
                util.log('B accept err:{}'.format(e))

    def B_recv(self, s, C_info, q):
        """B接收处理"""
        while True:
            try:
                # B接收到C
                r = s.recv(self.recv_size)
                if not r:
                    util.log("B connect broken:{}".format(C_info))
                    break
                # 加入队列
                q.put(r)
            except Exception as e:
                if isinstance(e, socket.timeout):
                    try:
                        # 判活
                        s.getsockname()
                    except:
                        s.close()
                        break
                    continue
                else:
                    util.log("B rev err:{}".format(e))
                    break
        try:
            s.close()
            S_info = self.CS_map[C_info]
            s = self.S_cons[S_info]
            s.close()
            del self.SC_map[S_info]
            del self.CS_map[C_info]
            del self.B_cons[C_info]
            del self.B_q[C_info]
            del self.S_cons[S_info]
        except Exception as e:
            util.log("disconnect B err:{}".format(e))
        util.log("B recv thread exit")

    def B_send(self, C_info):
        """B接收处理"""
        while True:
            try:
                while C_info not in self.CS_map:
                    continue
                S_info = self.CS_map[C_info]
                while S_info not in self.S_q:
                    continue
                q = self.S_q[S_info]
                # B接收到C
                r = q.get(timeout=self.queue_timeout)
                s = self.B_cons[C_info]
                # 转发给S
                s.send(r)
            except Exception as e:
                if isinstance(e,queue.Empty):
                    try:
                        s = self.B_cons[C_info]
                        # 判活
                        s.getsockname()
                    except:
                        break
                    continue
                else:
                    util.log("B send err:{}".format(e))
                    break
        util.log("B send thread exit")

    def A_accept(self, s):
        """A连接处理"""
        while True:
            a, _ = s.accept()
            a.settimeout(self.recv_timeout)
            S_info = a.getpeername()
            S_host = S_info[0]
            S_port = S_info[1]
            S_info = "{}_{}".format(S_host, str(S_port))
            q = queue.Queue(self.queue_size)
            # 创建S->A接收线程
            util.simple_thread(target=self.A_recv, args=(a, S_info, q))
            # 创建S->A->B->C发送线程;此时未得到C连接信息，传递S_info做索引
            util.simple_thread(target=self.A_send, args=(S_info,))
            self.S_cons[S_info] = a
            self.S_q[S_info] = q

            # 有S接入;找到配置中A->D的映射关系,发送给C,让客户端主动发起C->B链接
            A_port = a.getsockname()[1]
            A_port = str(A_port)
            C_host_id = self.port_map[A_port][0]
            D_host = self.port_map[A_port][1]
            D_port = self.port_map[A_port][2]
            cmd = {
                "type": "open",
                "s_host": S_host,
                "s_port": S_port,
                "d_host": D_host,
                "d_port": D_port,
            }
            self.cmd_send(C_host_id, cmd)

    def A_recv(self, s, S_info, q):
        """A接收处理"""
        while True:
            try:
                # S->A,A received
                r = s.recv(self.recv_size)
                if not r:
                    raise Exception("A connect broken:{}".format(S_info))
                q.put(r)
            except Exception as e:
                if isinstance(e,socket.timeout):
                    try:
                        # 判活
                        s.getsockname()
                    except:
                        s.close()
                        break
                    continue
                else:
                    util.log("A recv err:{}".format(e))
                    break
        try:
            # 断开B连接
            C_info = self.SC_map[S_info]
            s = self.B_cons[C_info]
            s.close()
            del self.SC_map[S_info]
            del self.CS_map[C_info]
            del self.S_cons[S_info]
            del self.S_q[S_info]
        except Exception as e:
            util.log("disconnect A err:{}".format(e))
        util.log("A recv thread exit")

    def A_send(self, S_info):
        """B接收处理"""
        while True:
            try:
                while S_info not in self.SC_map:
                    continue
                C_info = self.SC_map[S_info]
                while C_info not in self.B_q:
                    continue
                q = self.B_q[C_info]
                # B接收到C
                r = q.get(timeout=self.queue_timeout)
                s = self.S_cons[S_info]
                # 转发给S
                s.send(r)
            except Exception as e:
                if isinstance(e,queue.Empty):
                    try:
                        s = self.S_cons[S_info]
                        # 判活
                        s.getsockname()
                    except:
                        break
                    continue
                else:
                    util.log("A send err:{}".format(e))
                    break
        util.log("A send thread exit")

if __name__ == '__main__':
    foo = Host()
    foo.execute()
