import sys
import re
import ssl
import socket
import time
import threading
import binascii


DEFAULT_TIMEOUT = 1
DEFAULT_PORTS = '21-23,25,80,81,110,135,137,139,445,873,1433,1521,3306,3389,6379,7001,8000,8069,8080-8090,9000,9001,10051,11211'
DEFAULT_UDP_PORTS = '137' # NBNS
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36'


socket.setdefaulttimeout(DEFAULT_TIMEOUT)
lock = threading.Lock()  # for print

def to_ips(raw):
    if '/' in raw:
        addr, mask = raw.split('/')
        mask = int(mask)

        bin_addr = ''.join([ (8 - len(bin(int(i))[2:])) * '0' + bin(int(i))[2:] for i in  addr.split('.')])
        start = bin_addr[:mask] + (32 - mask) * '0'
        end = bin_addr[:mask] + (32 - mask) * '1'
        bin_addrs = [ (32 - len(bin(int(i))[2:])) * '0' + bin(i)[2:] for i in range(int(start, 2), int(end, 2) + 1)]

        dec_addrs = ['.'.join([str(int(bin_addr[8*i:8*(i+1)], 2)) for i in range(0, 4)]) for bin_addr in bin_addrs]                
        # print(dec_addrs)
        return dec_addrs
    elif '-' in raw:
        addr, end = raw.split('-')
        end = int(end)
        start = int(addr.split('.')[3])
        prefix = '.'.join(addr.split('.')[:-1])
        addrs = [ prefix + '.' + str(i) for i in range(start, end + 1) ]
        # print(addrs)
        return addrs
    else:
        return [raw]

        
def to_ports(raw):
    raw_ports = [i for i in raw.split(',')]
    ports = []
    for i in raw_ports:
        if '-' not in i:
            ports.append(int(i))
        else:
            start, end = i.split('-')
            ports += range(int(start), int(end)+1)
    return ports


def set_data(ip, port, flag):
    data = b'test_test\r\n'

    # TODO specifc UDP or TCP 
    if flag == 'U':
        if port == 137:  # NBNS 
            data = b'ff\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00 CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\x00\x00!\x00\x01'

    elif flag == 'T':
        if port == 21:
            data = b'pwd\r\n'
        elif port == 80:
            data = b'GET / HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\nConnection: close\r\n\r\n\r\n' % (ip.encode(), USER_AGENT.encode())
        elif port == 443:
            data = b'GET / HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\nConnection: close\r\n\r\n\r\n' % (ip.encode(), USER_AGENT.encode())
        elif port == 6379:
            data = b'INFO\r\n'
        elif port == 11211:
            data = b'stats items\r\n'
        else:
            data = b'unknownport\r\n\r\n'
    else:
        print('No protocol specifc ...')
        exit()

    return data


def check_rep(addr, port, rep, flag):
    # print((addr, port, rep, flag))
    if flag == 'U':
        if port == 137:  # parse NBNS may have problem
            num = ord(rep[56:57].decode())
            # print(num)
            data = rep[57:]
            ret = ''
            for i in range(num):
                name = data[18 * i:18 *i + 15].strip().decode()
                # print(name, data[18 * i + 15:18 *i + 16])
                # name_flag = data[18 * i + 16:18 *i + 18]
                if '__MSBROWSE__' not in name and name not in ret:
                    ret ='\\' + name + ret 
            return ret[1:]

        else:
            return rep
    elif flag == 'T':
        ret = ''
        if rep.startswith('HTTP/1.'):  # Http
            reps = rep.split('\\r\\n')  # has been addslashes so double \...
            ret += reps[0]

            for line in reps:
                if line.startswith('Server:') or line.startswith('Location:'):
                    # ret += line[line.find(':')+1:]
                    ret += '  ' + line
            
            r = re.search('<title>(.*?)</title>', rep)  # get title
            if r:
                ret += ' Title: ' + r.group(1)
            return ret

        elif port == 445: 
            """
            scan MS17-010 from xunfeng  
            """
            negotiate_protocol_request = binascii.unhexlify('00000054ff534d42720000000018012800000000000000000000000000002f4b0000c55e003100024c414e4d414e312e3000024c4d312e325830303200024e54204c414e4d414e20312e3000024e54204c4d20302e313200')
            session_setup_request = binascii.unhexlify('00000063ff534d42730000000018012000000000000000000000000000002f4b0000c55e0dff000000dfff02000100000000000000000000000000400000002600002e0057696e646f7773203230303020323139350057696e646f7773203230303020352e3000')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((addr, port))
                s.send(negotiate_protocol_request)
                s.recv(1024)
                s.send(session_setup_request)
                data = s.recv(1024)
                user_id = data[32:34]
                tree_connect_andx_request = '000000%xff534d42750000000018012000000000000000000000000000002f4b%sc55e04ff000000000001001a00005c5c%s5c49504324003f3f3f3f3f00' % ((58 + len(addr)), user_id.encode('hex'), addr.encode('hex'))
                s.send(binascii.unhexlify(tree_connect_andx_request))
                data = s.recv(1024)
                allid = data[28:36]
                payload = '0000004aff534d422500000000180128000000000000000000000000%s1000000000ffffffff0000000000000000000000004a0000004a0002002300000007005c504950455c00' % allid.encode('hex')
                s.send(binascii.unhexlify(payload))
                data = s.recv(1024)
                s.close()
                if '\x05\x02\x00\xc0' in data:
                    ret += '+Vulnerable+ MS 17-010    '
                else:
                    ret += 'MS 17-010 No Vulnerability    '
                s.close()
            except Exception as e:
                print(e)
                ret += 'MS 17-010 No Vulnerability    '
            try:
                payload1 = b'\x00\x00\x00\x85\xff\x53\x4d\x42\x72\x00\x00\x00\x00\x18\x53\xc8\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xfe\x00\x00\x00\x00\x00\x62\x00\x02\x50\x43\x20\x4e\x45\x54\x57\x4f\x52\x4b\x20\x50\x52\x4f\x47\x52\x41\x4d\x20\x31\x2e\x30\x00\x02\x4c\x41\x4e\x4d\x41\x4e\x31\x2e\x30\x00\x02\x57\x69\x6e\x64\x6f\x77\x73\x20\x66\x6f\x72\x20\x57\x6f\x72\x6b\x67\x72\x6f\x75\x70\x73\x20\x33\x2e\x31\x61\x00\x02\x4c\x4d\x31\x2e\x32\x58\x30\x30\x32\x00\x02\x4c\x41\x4e\x4d\x41\x4e\x32\x2e\x31\x00\x02\x4e\x54\x20\x4c\x4d\x20\x30\x2e\x31\x32\x00'
                payload2 = b'\x00\x00\x01\x0a\xff\x53\x4d\x42\x73\x00\x00\x00\x00\x18\x07\xc8\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xfe\x00\x00\x40\x00\x0c\xff\x00\x0a\x01\x04\x41\x32\x00\x00\x00\x00\x00\x00\x00\x4a\x00\x00\x00\x00\x00\xd4\x00\x00\xa0\xcf\x00\x60\x48\x06\x06\x2b\x06\x01\x05\x05\x02\xa0\x3e\x30\x3c\xa0\x0e\x30\x0c\x06\x0a\x2b\x06\x01\x04\x01\x82\x37\x02\x02\x0a\xa2\x2a\x04\x28\x4e\x54\x4c\x4d\x53\x53\x50\x00\x01\x00\x00\x00\x07\x82\x08\xa2\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\x02\xce\x0e\x00\x00\x00\x0f\x00\x57\x00\x69\x00\x6e\x00\x64\x00\x6f\x00\x77\x00\x73\x00\x20\x00\x53\x00\x65\x00\x72\x00\x76\x00\x65\x00\x72\x00\x20\x00\x32\x00\x30\x00\x30\x00\x33\x00\x20\x00\x33\x00\x37\x00\x39\x00\x30\x00\x20\x00\x53\x00\x65\x00\x72\x00\x76\x00\x69\x00\x63\x00\x65\x00\x20\x00\x50\x00\x61\x00\x63\x00\x6b\x00\x20\x00\x32\x00\x00\x00\x00\x00\x57\x00\x69\x00\x6e\x00\x64\x00\x6f\x00\x77\x00\x73\x00\x20\x00\x53\x00\x65\x00\x72\x00\x76\x00\x65\x00\x72\x00\x20\x00\x32\x00\x30\x00\x30\x00\x33\x00\x20\x00\x35\x00\x2e\x00\x32\x00\x00\x00\x00\x00'
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((addr, port))
                s.send(payload1)
                s.recv(1024)
                # print(s.recv(1024).replace(b'\x00', b'').decode(errors='ignore'))
                s.send(payload2)
                data = s.recv(1024)
                length = ord(data[43]) + ord(data[44]) * 256
                # print(length)
                data = data[47 + length:]
                # print(data.decode('UTF-16LE', errors='ignore').replace('\x00', '|'))
                ret += data.decode('UTF-16LE', errors='ignore').replace('\x00', '|')
            except Exception as e:
                ret += 'Fail to detect OS ...'
                print(e)
    
            return ret

        elif port == 6379 and not 'Authentication required' in rep:
            return '+Vulnerable+ Redis without password'

        else:
            return rep
    else:
        print('No protocol specifc ...')
        exit()


def thread(addr, ports, udp_ports):
    msg = ''
    # send udp nbns query

    for port in udp_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            data = set_data(addr, port, 'U')
            s.sendto(data, (addr, port))
            rep = s.recv(2000)
            if rep:
                rep = check_rep(addr, port, rep, 'U')
                msg += '  %s' % rep
        except socket.error as e:
            pass

    for port in ports:
        rep = ''
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((addr, port))
        except socket.error as e:  # close
            continue
        
        try:
            msg += '\n   %d   ' %  port
            data = set_data(addr, port, 'T')  # TODO set data according port num 
            if port == 443:
                s = ssl.wrap_socket(s)
            s.send(data)

            rep = s.recv(2000)
        except socket.error as e:
            # print(e)
            pass

        try:    
            # msg += banner.replace('\n', '\\n').replace('\r', '\\r') if isinstance(banner, str) else banner.decode('utf-8', errors='replace') # .replace(b'\n', b'\\n').replace(b'\r', b'\\r') # decode and pring banner
            if isinstance(rep, str):
                tmp_rep = rep.decode('utf-8', errors='ignore').encode('utf-8').replace('\n', '\\n').replace('\r', '\\r')
            else:
                tmp_rep = rep.decode('utf-8', errors='ignore').replace('\n', '\\n').replace('\r', '\\r')

            tmp_rep = check_rep(addr, port, tmp_rep, 'T')  # Exception in function ??
            msg += tmp_rep
        except Exception as e:
            print('Encoding error ? ', e)
            print(addr, port)
            print(rep)

    if msg:
        lock.acquire()
        print('[*]' + addr + ' ' + msg)
        lock.release()

def handle_input():
    if len(sys.argv) != 2 and len(sys.argv) != 3 and len(sys.argv) != 4:
        # print('*********************************************************')
        # print('     A simple muti-threading port scanner By: iiiiii     ')
        # print('     https://github.com/iiilin/ASimplePortScanner        ')
        # print('*********************************************************')
        # print('Default tcp port: ' + DEFAULT_PORTS)
        # print('Default udp port: ' + DEFAULT_UDP_PORTS)
        print('Usage:')
        print('python scan.py ip [UT] [ports]')
        print('Example:')
        print('python scan.py 10.19.38.0/24')
        print('python scan.py 10.19.38.0-254')
        print('python scan.py 10.19.38.8 U')
        print('python scan.py 10.19.38.8 T 22,23,24,25,1000-10086,22722')
        # print('*********************************************************')
        exit() 

    if len(sys.argv) >= 2:
        hosts = to_ips(sys.argv[1])
        ports = to_ports(DEFAULT_PORTS)
        udp_ports = to_ports(DEFAULT_UDP_PORTS)  # always udp

    if len(sys.argv) >= 3:

        if 'T' not in sys.argv[2]:
            ports = []
        elif 'U' not in sys.argv[2]:
            udp_ports = []
    
    if len(sys.argv) >= 4:
        ports = to_ports(sys.argv[3])
    
    return hosts, ports, udp_ports

def main():
    hosts, ports, udp_ports = handle_input()
    start = time.time()
    pool = [ threading.Thread(target=thread, args=(host, ports, udp_ports)) for host in hosts]
    for t in pool:
        t.start()
    for t in pool:
        t.join()

    print('Finish...')
    print('Cost time: %.2f' % (time.time() - start))

main()
# print(check_rep('172.16.9.250', 445, '', 'T'))