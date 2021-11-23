###
概览
- python version >= 3
- 主打轻量化,官方自带包:socket/queue/threading等,无需额外包
- 多线程队列通信，支持多对多设备
- 实测速度无损耗，速度取决于内网上传带宽和公网机器带宽

###
网络模型说明
####
S->[A->B]->[C->D]
参考"网络模型图.jpg"

- S:外网机器
- A:公网机器与外网机器通信的端口
- B:公网机器与内网机器通信的端口
- C:内网机器与公网机器通信的端口
- D:内网机器被转发到外网的设备

![img](https://github.com/freevolunteer/neddle/blob/master/%E7%BD%91%E7%BB%9C%E6%A8%A1%E5%9E%8B%E5%9B%BE.jpg?raw=true)

###
使用说明
公网host部署host.py,参考:
> nohup /usr/local/bin/python3 -u /root/host.py>> /root/log/host.log &

内网local部署local.py,参考:
> nohup /usr/local/bin/python3 -u /root/local.py>> /root/log/local.log &

###
网络安全提醒
暴露端口有风险,不必要时，可停止host.py运行

###
host参考配置
```json
{
  "host": {
    "bind_addr": "0.0.0.0",
    "ctl_port": 4890,
    "B_port": 4891,
    "port_map": {
      "4892": ["zbox", "127.0.0.1", 22],
      "4893": ["zbox", "192.168.3.32", 22],
      "4894": ["nas", "127.0.0.1", 3306]
    },
    "recv_size": 1024,
    "queue_size": 1024
  }
}
```
- 确认ctl_port和B_port有对外权限，

###
local参考配置
```json
{
  "local": {
    "id": "zbox",
    "host_addr": "111.111.111.111",
    "ctl_port": 4890,
    "B_port": 4891,
    "recv_size": 1024,
    "queue_size": 1024
  }
}
```
- ctl_port和B_port应与公网host对应端口一致
- host_addr为公网host ip
- id为local机器的唯一标志，不能重复

###
举例说明
以上述配置为例：
内网机器zbox部署local.py
另一内网机器nas部署local.py
公网机器部署host.py,IP为111.111.111.111

外网设备client登录zbox本身:
> ssh -p4892 root@111.111.111.111

等效于client处在zbox网络位置ssh -p22 root@127.0.0.1

 外网设备client登录zbox所在内网的设备192.168.3.32:
> ssh -p4893 root@111.111.111.111

等效于client处在zbox网络位置ssh -p22 root@192.168.3.32,注意是以client身份登录而非zbox,支持公钥免密登录


外网设备client连接nas上的mysql:
> mysql -h111.111.111.111 -P4894 -uroot -p

等效于client处在nas网络位置mysql -h127.0.0.1 -P3306 -uroot -p




