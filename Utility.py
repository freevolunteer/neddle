import threading
import traceback
import time

def log(msg=''):
    if not msg:
        return 
    file = traceback.extract_stack()[-2][0]
    line = traceback.extract_stack()[-2][1]
    date = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = '{} {}:{} {}'.format(date,file,line, msg)
    print(msg)

def simple_thread(target, args, daemon=True):
    try:
        t = threading.Thread(target=target, args=args)
        t.daemon = daemon
        t.start()
        return t
    except Exception as e:
        log('get thread fail:{}'.format(e))