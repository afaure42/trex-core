from .cap_handling import pcap_reader
from .arg_verify import ArgVerify
import os
import sys
import inspect
from .trex_astf_exceptions import ASTFError, ASTFErrorBadParamCombination, ASTFErrorMissingParam, ASTFErrorOverlapIP
from .trex_astf_global_info import ASTFGlobalInfo, ASTFGlobalInfoPerTemplate
import json
import base64
import hashlib
import traceback
from ..common.trex_exceptions import *
from ..common.trex_types import listify
from ..utils.common import ip2int
import imp
import collections

def pretty_exceptions(func):
    def pretty_exceptions_inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            a, b, tb = sys.exc_info()
            x =''.join(traceback.format_list(traceback.extract_tb(tb)[1:])) + a.__name__ + ": " + str(b) + "\n"

            summary = "\nPython Traceback follows:\n\n" + x
            raise TRexError(summary)
    return pretty_exceptions_inner

class _ASTFCapPath(object):
    @classmethod
    def get_pcap_file_path(cls, pcap_file_name):
        f_path = pcap_file_name
        if not os.path.isabs(pcap_file_name):
            p = cls.get_path_relative_to_profile()
            if p:
                f_path = os.path.abspath(os.path.join(os.path.dirname(p), pcap_file_name))

        return f_path

    @staticmethod
    def get_path_relative_to_profile():
        p = inspect.stack()
        for obj in p:
            if obj[3] == 'get_profile':
                return obj[1]
        return None


class ASTFCmd(object):
    def __init__(self):
        self.fields = {}
        self.stream=None
        self.buffer=None


    def to_json(self):
        return dict(self.fields)

    def dump(self):
        ret = "{0}".format(self.__class__.__name__)
        return ret


class ASTFCmdTxPkt(ASTFCmd):
    def __init__(self, buf, size=0, fill=None):
        super(ASTFCmdTxPkt, self).__init__()
        self._buf = base64.b64encode(buf).decode()
        self.fields['name'] = 'tx_msg'
        self.fields['buf_index'] = -1
        self.buffer_len = len(buf)  # buf len before decode
        if size > len(buf):
            self._buf = { "base": self._buf, "size": size }
            if fill is not None:
                if type(fill) is not bytes:
                    fill = fill.encode('ascii')
                self._buf["fill"] = base64.b64encode(fill).decode()
            self.buffer_len = size
        self.stream=False
        self.buffer=True;

    @property
    def buf_len(self):
        return self.buffer_len

    @property
    def buf(self):
        return self._buf

    @property
    def buf_index(self):
        return self.fields['buf_index']

    @buf_index.setter
    def index(self, index):
        self.fields['buf_index'] = index

    def dump(self):
        ret = "{0}(\"\"\"{1}\"\"\")".format(self.__class__.__name__, self.buf)
        return ret


class ASTFCmdSend(ASTFCmd):
    def __init__(self, buf, size=0, fill=None):
        super(ASTFCmdSend, self).__init__()
        self._buf = base64.b64encode(buf).decode()
        self.fields['name'] = 'tx'
        self.fields['buf_index'] = -1
        self.buffer_len = len(buf)  # buf len before decode
        if size > len(buf):
            self._buf = { "base": self._buf, "size": size }
            if fill is not None:
                if type(fill) is not bytes:
                    fill = fill.encode('ascii')
                self._buf["fill"] = base64.b64encode(fill).decode()
            self.buffer_len = size
        self.stream=True
        self.buffer=True;

    @property
    def buf_len(self):
        return self.buffer_len

    @property
    def buf(self):
        return self._buf

    @property
    def buf_index(self):
        return self.fields['buf_index']

    @buf_index.setter
    def index(self, index):
        self.fields['buf_index'] = index

    def dump(self):
        ret = "{0}(\"\"\"{1}\"\"\")".format(self.__class__.__name__, self.buf)
        return ret

class ASTFCmdKeepaliveMsg(ASTFCmd):
    def __init__(self, msec, rx_mode=False):
        super(ASTFCmdKeepaliveMsg, self).__init__()
        self.fields['name'] = 'keepalive'
        self.fields['msec'] = msec
        if rx_mode:
            self.fields['rx_mode'] = rx_mode
        self.stream=False


class ASTFCmdRecvMsg(ASTFCmd):
    def __init__(self, min_pkts,clear=False):
        super(ASTFCmdRecvMsg, self).__init__()
        self.fields['name'] = 'rx_msg'
        self.fields['min_pkts'] = min_pkts
        if clear:
            self.fields['clear'] = True
        self.stream=False

    def dump(self):
        ret = "{0}({1})".format(self.__class__.__name__, self.fields['min_pkts'])
        return ret


class ASTFCmdRecv(ASTFCmd):
    def __init__(self, min_bytes,clear=False):
        super(ASTFCmdRecv, self).__init__()
        self.fields['name'] = 'rx'
        self.fields['min_bytes'] = min_bytes
        if clear:
            self.fields['clear'] = True
        self.stream=True

    def dump(self):
        ret = "{0}({1})".format(self.__class__.__name__, self.fields['min_bytes'])
        return ret

class ASTFCmdCloseMsg(ASTFCmd):
    def __init__(self):
        super(ASTFCmdCloseMsg, self).__init__()
        self.fields['name'] = 'close_msg'
        self.stream=False


class ASTFCmdDelay(ASTFCmd):
    def __init__(self, usec):
        super(ASTFCmdDelay, self).__init__()
        self.fields['name'] = 'delay'
        self.fields['usec'] = usec

class ASTFCmdReset(ASTFCmd):
    def __init__(self):
        super(ASTFCmdReset, self).__init__()
        self.fields['name'] = 'reset'
        self.stream=True

class ASTFCmdNoClose(ASTFCmd):
    def __init__(self):
        super(ASTFCmdNoClose, self).__init__()
        self.fields['name'] = 'nc'
        self.stream=True

class ASTFCmdConnect(ASTFCmd):
    def __init__(self):
        super(ASTFCmdConnect, self).__init__()
        self.fields['name'] = 'connect'
        self.stream=True

class ASTFCmdDelayRnd(ASTFCmd):
    def __init__(self,min_usec,max_usec):
        super(ASTFCmdDelayRnd, self).__init__()
        self.fields['name'] = 'delay_rnd'
        self.fields['min_usec'] = min_usec
        self.fields['max_usec'] = max_usec

# Set Val Commands #
class ASTFCmdSetValBase(ASTFCmd):
    def __init__(self, id_val):
        super(ASTFCmdSetValBase, self).__init__()
        self.fields['id'] = id_val

class ASTFCmdSetVal(ASTFCmdSetValBase):
    def __init__(self, id_val, val):
        super(ASTFCmdSetVal, self).__init__(id_val)
        self.fields['name'] = 'set_var'
        self.fields['val']  = val

class ASTFCmdAddVal(ASTFCmdSetValBase):
    def __init__(self, id_val, val):
        super(ASTFCmdAddVal, self).__init__(id_val)
        self.fields['name'] = 'add_var'
        self.fields['val']  = val

# Set Tick Val Commands #
class ASTFCmdSetTickValBase(ASTFCmd):
    def __init__(self, id_val):
        super(ASTFCmdSetTickValBase, self).__init__()
        self.fields['id'] = id_val

class ASTFCmdSetTickVar(ASTFCmdSetTickValBase):
    def __init__(self, id_val):
        super(ASTFCmdSetTickVar, self).__init__(id_val)
        self.fields['name'] = 'set_tick_var'

class ASTFCmdAddTickVar(ASTFCmdSetTickValBase):
    def __init__(self, id_val, duration):
        super(ASTFCmdAddTickVar, self).__init__(id_val)
        self.fields['name'] = 'add_tick_var'
        self.fields['duration']  = duration

# Add Statistics Commands #
class ASTFCmdAddStatsBase(ASTFCmd):
    def __init__(self, id_val):
        super(ASTFCmdAddStatsBase, self).__init__()
        self.fields['stats_id'] = id_val

class ASTFCmdAddStatsVal(ASTFCmdAddStatsBase):
    def __init__(self, id_val, val):
        super(ASTFCmdAddStatsVal, self).__init__(id_val)
        self.fields['name'] = 'add_stats'
        self.fields['val']  = val

class ASTFCmdAddTickStats(ASTFCmdAddStatsBase):
    def __init__(self, id_val, tick_var):
        super(ASTFCmdAddTickStats, self).__init__(id_val)
        self.fields['name'] = 'add_tick_stats'
        self.fields['var_id']  = tick_var

# Conditional Jump Commands #
class ASTFCmdJMPBase(ASTFCmd):
    def __init__(self, id_val, offset, label):
        super(ASTFCmdJMPBase, self).__init__()
        self.label            = label
        self.fields['id']     = id_val
        self.fields['offset'] = offset

class ASTFCmdJMPNZ(ASTFCmdJMPBase):
    def __init__(self, id_val, offset,label):
        super(ASTFCmdJMPNZ, self).__init__(id_val, offset, label)
        self.fields['name'] = 'jmp_nz'

class ASTFCmdJMPDP(ASTFCmdJMPBase):
    def __init__(self, id_val, offset, label, duration):
        super(ASTFCmdJMPDP, self).__init__(id_val, offset, label)
        self.fields['name'] = 'jmp_dp'
        self.fields['duration'] = duration

class ASTFCmdJMPCMP(ASTFCmdJMPBase):
    def __init__(self, id_val, offset, label, cmp_op, cmp_val):
        super(ASTFCmdJMPCMP, self).__init__(id_val, offset, label)
        self.fields['name'] = 'jmp_cmp'
        if not id_val:
            del self.fields['id']
        else:
            self.fields['cmp_op'] = cmp_op
            self.fields['cmp_val'] = cmp_val

class ASTFCmdTxMode(ASTFCmd):
    def __init__(self,flags):
        super(ASTFCmdTxMode, self).__init__()
        self.fields['name'] = 'tx_mode'
        self.fields['flags'] = flags

# Template Control Commands #
class ASTFCmdSetTemplate(ASTFCmd):
    def __init__(self, id_val):
        super(ASTFCmdSetTemplate, self).__init__()
        self.fields['name'] = 'set_template'
        self.fields['tg_id'] =  id_val

class ASTFCmdExecTemplate(ASTFCmd):
    def __init__(self):
        super(ASTFCmdExecTemplate, self).__init__()
        self.fields['name'] = 'exec_template'


class ASTFProgram(object):
    """

       Emulation L7 program

       .. code-block:: python

            # server commands
            prog_s = ASTFProgram()
            prog_s.recv(len(http_req))
            prog_s.send(http_response)
            prog_s.delay(10)
            prog_s.reset()




     """

    MIN_DELAY = 50 
    MAX_DELAY = 700000 
    MAX_KEEPALIVE = 500000 

    def __init__(self, file=None, side="c", commands=None,stream=True, s_delay=None, udp_mtu=None, addon=None):
        """

        :parameters:

                  file : string
                     pcap file to analyze

                  side : string
                        "c" for client side or "s" for server side

                  commands   : list
                        list of command objects cound be NULL in case you call the API

                  stream    : bool
                     is stream based (TCP) or packet based (UDP)
                    
                  s_delay : ASTFCmdDelay or ASTFCmdDelayRnd see :class:`trex.astf.trex_astf_profile.ASTFCmdDelay` and :class:`trex.astf.trex_astf_profile.ASTFCmdDelayRnd`
                      Server delay command before sending response back to client. This will override ASTFProfile s_delay if supplied. defaults to None means no delay.

                  udp_mtu: int or None
                      MTU for udp packets, if packets exceeding the specified value they will be cut down from L7 in order to fit. defaults to None.

                  addon : string
                      add-on name to handle data between program and base protocol.


        """

        ver_args = {"types":
                    [{"name": "file", 'arg': file, "t": str, "must": False},
                     {"name": "commands", 'arg': commands, "t": ASTFCmd, "must": False, "allow_list": True},
                     {"name": "s_delay", 'arg': s_delay, "t": [ASTFCmdDelay, ASTFCmdDelayRnd], "must": False},
                     {"name": "udp_mtu", 'arg': udp_mtu, "t": int, "must": False},
                     {"name": "addon", 'arg': addon, "t": str, "must": False},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)
        side_vals = ["c", "s"]
        if side not in side_vals:
            raise ASTFError("Side must be one of {0}".side_vals)

        self.vars={};
        self.tick_vars={};
        self.stream=stream;
        self.labels={};
        self.fields = {}
        self.fields['commands'] = []
        self.total_send_bytes = 0
        self.total_rcv_bytes = 0
        self.udp_mtu = udp_mtu
        self.s_delay = s_delay
        self.addon = addon
        if file is not None:
            cap = pcap_reader(_ASTFCapPath.get_pcap_file_path(file))
            cap.analyze()
            self._p_len = cap.payload_len
            is_tcp=cap.is_tcp()
            if is_tcp:
                cap.condense_pkt_data()
            else:
                self.stream=False
            
            self._create_cmds_from_cap(is_tcp,cap.pkts,cap.pkt_times,cap.pkt_dirs, side)
        elif commands is not None:
            self._set_cmds(listify(commands))

    def update_keepalive (self,prog_s):
        """ in case of pcap file need to copy the keepalive command from client to server side 
        """
        if len(self.fields['commands'])>0:
            cmd=self.fields['commands'][0];
            if isinstance(cmd, ASTFCmdKeepaliveMsg):
                prog_s.fields['commands'].insert(0,cmd);


    def is_stream(self):
        return self.stream

    def calc_hash(self):
        return hashlib.sha256(repr(self.to_json()).encode()).digest()

    def send_chunk(self, l7_buf,chunk_size,delay_usec):
        """
        Send l7_buffer by splitting it into small chunks and issue a delay betwean each chunk. 
        This is a utility  command that works on top of send/delay command

         example1
          send (buffer1,100,10) will split the buffer to buffers of 100 bytes with delay of 10usec

        :parameters:

                  l7_buf : string
                     l7 stream as string 

                  chunk_size : uint32_t 
                     size of each chunk 

                  delay_usec : uint32_t 
                     the delay in usec to insert betwean each write 
        """
        ver_args = {"types":
                    [
                    {"name": "l7_buf", 'arg': l7_buf, "t": [bytes, str]},
                    {"name": "chunk_size", 'arg': chunk_size, "t": [int]},
                    {"name": "delay_usec", 'arg': delay_usec, "t": [int]},
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        enc_buf=self._c_b (l7_buf)
        size=len(enc_buf);
        cnt=0;
        while size>0 :
            self.send(enc_buf[cnt:cnt+chunk_size])
            if delay_usec:
                self.delay(delay_usec);
            cnt+=chunk_size;
            size-=chunk_size;

    def close_msg (self):
        """
        explicit UDP flow close 


        """
        self.fields['commands'].append(ASTFCmdCloseMsg())

    def _c_b (self,buf):

        #Python2 string and bytes are the same 
        if type(buf) is bytes:
            return buf;
        try:
            enc_buf = buf.encode('ascii')
            return enc_buf
        except UnicodeEncodeError as e:
            print (e)
            raise ASTFError("If buf is a string, it must contain only ascii")


    def send_msg (self, buf, size=0, fill=None):
        """
        send UDP message (buf) 

         example1
          send_msg (buffer1)
          recv_msg (1)


        :parameters:
                  buf : string
                     l7 stream as string 
                  size : uint32_t
                     total size of l7 stream, effective only when size > len(buf).
                  fill : string
                     l7 stream filled by string, only if size is effective.

        """
        ver_args = {"types":
                    [ {"name": "buf", 'arg': buf, "t": [bytes, str]},
                      {"name": "size", 'arg': size, "t": int, "must": False},
                      {"name": "fill", 'arg': fill, "t": [bytes, str], "must": False}
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        # we support bytes or ascii strings
        enc_buf=self._c_b (buf)

        cmd = ASTFCmdTxPkt(enc_buf, size, fill)
        self.total_send_bytes += cmd.buf_len
        cmd.index = None
        self.fields['commands'].append(cmd)

    def set_send_blocking (self,block):
        """
           set_send_blocking (block), set the stream transmit mode 

           block : for send command wait until the last byte is ack 

           non-block: continue to the next command when the queue is almost empty, this is good for pipeline the transmit 

        :parameters:
                  block  : bool

        """
        ver_args = {"types":
                    [{"name": "block", 'arg': block, "t": bool}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)
        if block:
            flags = 0
        else:
            flags = 1

        self.fields['commands'].append(ASTFCmdTxMode(flags))

    def set_keepalive_msg (self,msec,rx_mode=False):
        """
        set_keepalive_msg (msec), set the keepalive timer for UDP flows 

        :parameters:
                  msec  : uint32_t
                   the keepalive time in msec 
                  rx_mode  : bool
                   reset by rx packets only. i.e. send_msg does not reset the keepalive timer.
        """

        ver_args = {"types":
                    [{"name": "msec", 'arg': msec, "t": int},
                     {"name": "rx_mode", 'arg': rx_mode, "t": bool, "must": False}
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdKeepaliveMsg(msec, rx_mode))


    def recv_msg(self, pkts,clear=False):
        """
        recv_msg (pkts)

        works for UDP flow 

        :parameters:
                  pkts  : uint64_t
                   wait until the rx packet watermark is reached on flow counter.  

                  clear  : bool
                     when reach the watermark clear the flow counter 

        """

        ver_args = {"types":
                    [ {"name": "pkts", 'arg': pkts, "t": int},
                      {"name": "clear", 'arg': clear, "t": [int,bool], "must": False}
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.total_rcv_bytes += pkts
        self.fields['commands'].append(ASTFCmdRecvMsg(self.total_rcv_bytes,clear))
        if clear:
            self.total_rcv_bytes = 0


    def send(self, buf, size=0, fill=None):
        """
        send (l7_buffer) over TCP and wait for the buffer to be acked by peer. Rx side could work in parallel

         example1
          send (buffer1)
          send (buffer2)

           Will behave differently than 

         example1
         send (buffer1+ buffer2)

        in the first example there would be PUSH in the last byte of the buffer and immediate ACK from peer while in the last example the buffer will be sent together (might be one segment)

        :parameters:
                  buf : string
                     l7 stream as string 
                  size : uint32_t
                     total size of l7 stream, effective only when size > len(buf).
                  fill : string
                     l7 stream filled by string, only if size is effective.

        """

        ver_args = {"types":
                    [ {"name": "buf", 'arg': buf, "t": [bytes, str]},
                      {"name": "size", 'arg': size, "t": int, "must": False},
                      {"name": "fill", 'arg': fill, "t": [bytes, str], "must": False}
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        # we support bytes or ascii strings
        enc_buf=self._c_b (buf)
        cmd = ASTFCmdSend(enc_buf, size, fill)
        self.total_send_bytes += cmd.buf_len
        cmd.index = None
        self.fields['commands'].append(cmd)

    def recv(self, bytes,clear=False):
        """
        recv (bytes)

        :parameters:
                  bytes  : uint64_t
                   wait until the rx bytes watermark is reached on flow counter.  

                  clear  : bool
                     when reach the watermark clear the flow counter 
        """

        ver_args = {"types":
                    [ {"name": "bytes", 'arg': bytes, "t": int},
                      {"name": "clear", 'arg': clear, "t": [int,bool], "must": False},
                    ]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.total_rcv_bytes += bytes
        self.fields['commands'].append(ASTFCmdRecv(self.total_rcv_bytes,clear))
        if clear:
            self.total_rcv_bytes = 0

    def delay(self, usec):
        """
        delay for x usec

        :parameters:
                  usec  : uint32_t
                   delay for this time in usec

        """

        ver_args = {"types":
                    [{"name": "usec", 'arg': usec, "t": [int, float]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdDelay(usec))

    def reset(self):
        """
        For TCP connection send RST to peer. Should be the last command 

        """

        self.fields['commands'].append(ASTFCmdReset())

    def wait_for_peer_close(self):
        """
        For TCP connection wait for peer side to close (read==0) and only then close. Should be the last command
        This simulates server side that waits for a requests until client retire with close().

        """

        self.fields['commands'].append(ASTFCmdNoClose())

    def connect(self):
        """
        for TCP connection wait for the connection to be connected. should be the first command in the client side
        """

        self.fields['commands'].append(ASTFCmdConnect())

    def accept(self):
        """
        for TCP connection wait for the connection to be accepted. should be the first command in the server side 
        """
    
        self.fields['commands'].append(ASTFCmdConnect())


    def delay_rand(self, min_usec,max_usec):
        """
        delay for a random time betwean  min-max usec with uniform distribution

        :parameters:
                  min_usec  : float
                     min delay for this time in usec

                  max_usec  : float
                     min delay for this time in usec

        """

        ver_args = {"types":
                    [{"name": "min_usec", 'arg': min_usec, "t": [int, float]},
                     {"name": "max_usec", 'arg': min_usec, "t": [int, float]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        if min_usec>max_usec:
                raise ASTFError("min value {0} is bigger than max {1}  ".format(min_usec,max_usec))

        self.fields['commands'].append(ASTFCmdDelayRnd(min_usec,max_usec))

    def __add_var (self,var_name):
        if var_name not in self.vars:
            var_index=len(self.vars);
            self.vars[var_name]=var_index

    def __add_tick_var (self,var_name):
        if var_name not in self.tick_vars:
            var_index=len(self.tick_vars);
            self.tick_vars[var_name]=var_index

    def __get_var_index (self,var_name):
        if var_name not in self.vars:
            raise ASTFError("var {0} wasn't defined  ".format(var_name))
        return (self.vars[var_name]);

    def __get_tick_var_index (self,var_name):
        if var_name not in self.tick_vars:
            raise ASTFError("var {0} wasn't defined  ".format(var_name))
        return (self.tick_vars[var_name]);

    def set_var(self, var_id,val):
        """
        Set a flow variable 

        :parameters:
                  var_id  : string
                     var-id there are limited number of variables 

                  val  : uint64_t
                     value of the variable 

        """

        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "val", 'arg': val, "t": [int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        if  isinstance(var_id, str):
            self.__add_var(var_id)
        self.fields['commands'].append(ASTFCmdSetVal(var_id,val))

    def add_var(self, var_id, val):
        """
        Add a value to a flow variable

        :parameters:
            var_id  : string
                var-id there are limited number of variables

            val  : int
                value to be added

        """
        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "val", 'arg': val, "t": [int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdAddVal(var_id,val))

    def set_tick_var(self, var_id):
        """
        Set a flow variable used with jmp_nz command. Timer will be started when declaring tick var. 

        :parameters:
            var_id  : string
                var-id there are limited number of variables
        """
        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        if  isinstance(var_id, str):
            self.__add_tick_var(var_id)
        self.fields['commands'].append(ASTFCmdSetTickVar(var_id))

    def add_tick_var(self, var_id, duration):
        """
        Add a tick value to a flow variable

        :parameters:
            var_id  : string
               var-id there are limited number of variables

            duartion  : float
               duration of time in seconds to be added

        """
        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "duration", 'arg': duration, "t": [float, int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdAddTickVar(var_id,duration))

    def add_stats(self, stats_id, val):
        """
        Add counter value to a statistics counter

        :parameters:
            stats_id  : int or string
               statistics counter index (0, 1, 2, ... or 'A', 'B', 'C', ...)

            val  : uint64_t
               counter value to be added

        """
        ver_args = {"types":
                    [{"name": "stats_id", 'arg': stats_id, "t": [int, str]},
                     {"name": "val", 'arg': val, "t": [int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        if isinstance(stats_id, str):
            stats_id = ord(stats_id.upper()) - ord('A')

        self.fields['commands'].append(ASTFCmdAddStatsVal(stats_id,val))

    def add_tick_stats(self, stats_id, var_id):
        """
        Add elapsed time from a flow tick variable to a statistics counter

        :parameters:
            stats_id  : int or string
               statistics counter index (0, 1, 2, ... or 'A', 'B', 'C', ...)

            var_id  : string
               flow tick variable that the base time is saved

        """
        ver_args = {"types":
                    [{"name": "stats_id", 'arg': stats_id, "t": [int, str]},
                     {"name": "var_id", 'arg': var_id, "t": [str]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        if isinstance(stats_id, str):
            stats_id = ord(stats_id.upper()) - ord('A')

        self.fields['commands'].append(ASTFCmdAddTickStats(stats_id,var_id))

    def set_label(self, label):
        """
        Set a location label name. used with jmp_nz command 
        """
        if label in self.labels:
            raise ASTFError("label {0} was defined already ".format(label))

        #print("label {0} offset {1} ".format(label,len(self.fields['commands'])))
        self.labels[label]=len(self.fields['commands']);

    def __get_label_id (self,label):
        if label not in self.labels:
            raise ASTFError("label {0} wasn't defined ".format(label))
        return(self.labels[label]);

    def jmp_nz(self, var_id,label):
        """
        Decrement the flow variable, in case of none zero jump to label 

        :parameters:
                  var_id  : int
                     flow var id 

                  label  : string
                     label id

        """

        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "label", 'arg': label, "t": [str]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdJMPNZ(var_id,0,label))

    def jmp_dp(self, var_id, label, duration):
        """
        Check the time passed from flow variable, in case of time passed is less then duration jump to label.

        :parameters:
            var_id  : int
                flow var id 

            label  : string
                label id

            duration : double
                duration of time in seconds
        """
        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "label", 'arg': label, "t": [str]},
                     {"name": "duration", 'arg': duration, "t": [float, int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)
        duration = float(duration)
        self.fields['commands'].append(ASTFCmdJMPDP(var_id, 0, label, duration))

    def jmp_cmp(self, var_id, label, cmp_op, cmp_val):
        """
        Jump to label if the result of comparison operation is true.

        :parameters:
            var_id  : string
                flow var id

            label  : string
                label id

            cmp_op  : string
                comparison operator: 'lt', 'gt', 'eq', 'ge', 'le', 'ne'

            cmp_val  : int
                a value to compare with flow variable id

        """

        ver_args = {"types":
                    [{"name": "var_id", 'arg': var_id, "t": [str]},
                     {"name": "label", 'arg': label, "t": [str]},
                     {"name": "cmp_op", 'arg': cmp_op, "t": [str]},
                     {"name": "cmp_val", 'arg': cmp_val, "t": [int]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdJMPCMP(var_id, 0, label, cmp_op, cmp_val))

    def jmp(self, label):
        self.jmp_cmp('', label, '', 0)

    def jmp_lt(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'lt', value)

    def jmp_gt(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'gt', value)

    def jmp_eq(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'eq', value)

    def jmp_ge(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'ge', value)

    def jmp_le(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'le', value)

    def jmp_ne(self, var_id, label, value):
        self.jmp_cmp(var_id, label, 'ne', value)


    def set_next_template(self, tg_id):
        """
        Set next template to generate new flow with the same association

        :parameters:
            tg_name  : string
                template name to generate new flow
        """
        ver_args = {"types":
                    [{"name": "tg_id", 'arg': tg_id, "t": [str]}]
                    }
        ArgVerify.verify(self.__class__.__name__ + "." + sys._getframe().f_code.co_name, ver_args)

        self.fields['commands'].append(ASTFCmdSetTemplate(tg_id))

    def exec_template(self):
        """
        Generate a flow from given template and wait for it done

        """
        self.fields['commands'].append(ASTFCmdExecTemplate())


    def _set_cmds(self, cmds):
        for cmd in cmds:
            if cmd.buffer:
                self.total_send_bytes += cmd.buf_len
                cmd.index = None
            self.fields['commands'].append(cmd)

    def _create_cmds_from_cap(self, is_tcp, cmds, times, dirs, init_side):
        assert len(cmds) == len(dirs)
        if not cmds:
            return
        new_cmds = []
        tot_rcv_bytes = 0
        rx=False
        max_delay=0;

        if is_tcp:
            # In case that server start sending the traffic we must wait for the connection to establish
            if dirs[0] == 's' and init_side == 's':
                new_cmds.append(ASTFCmdConnect())

            for cmd, dir in zip(cmds, dirs):
                if dir == init_side:
                    new_cmd = ASTFCmdSend(cmd.payload)
                else:
                    # Server need to see total rcv bytes, and not amount for each packet
                    tot_rcv_bytes += len(cmd.payload)
                    new_cmd = ASTFCmdRecv(tot_rcv_bytes)
                new_cmds.append(new_cmd)
        else:
            assert len(cmds) == len(times)
            last_dir=None
            non_l7_len = 14 + 20 + 8  # Ethernet, IP, UDP
            if self.udp_mtu is not None:
                assert self.udp_mtu > non_l7_len, 'udp_mtu cannot be smaller than 42! (sum of L2-4)'
            max_payload_allowed = float('inf') if self.udp_mtu is None else self.udp_mtu - (non_l7_len)
            for cmd, time, dir in zip(cmds, times, dirs):
                if len(cmd.payload) > max_payload_allowed:
                    cmd.payload = cmd.payload[:max_payload_allowed]

                if dir == init_side:
                    if last_dir == init_side:
                        dusec=int(time*1000000)
                        if dusec > ASTFProgram.MAX_DELAY:
                            dusec =ASTFProgram.MAX_DELAY;
                        if dusec>ASTFProgram.MIN_DELAY:
                           ncmd = ASTFCmdDelay(dusec)
                           if max_delay<dusec:
                               max_delay=dusec
                           new_cmds.append(ncmd)
                    else:
                        if rx:
                          rx=False
                          ncmd = ASTFCmdRecvMsg(tot_rcv_bytes)
                          new_cmds.append(ncmd)

                    new_cmd = ASTFCmdTxPkt(cmd.payload)
                    new_cmds.append(new_cmd)
                else:
                    tot_rcv_bytes += 1
                    rx=True
                last_dir=dir;

        if rx:
          rx=False
          ncmd = ASTFCmdRecvMsg(tot_rcv_bytes)
          new_cmds.append(ncmd)
        if max_delay> ASTFProgram.MAX_KEEPALIVE:
            new_cmds.insert(0,ASTFCmdKeepaliveMsg(max_delay*2))
        if self.s_delay is not None and init_side == 's':
            new_cmds = self._add_server_delay(new_cmds)                

        if not is_tcp:
            max_delay = 0
            for cmd in new_cmds:
                if isinstance(cmd, ASTFCmdDelay):
                    max_delay = max(max_delay, cmd.fields['usec'])
                if isinstance(cmd, ASTFCmdDelayRnd):
                    max_delay = max(max_delay, cmd.fields['max_usec'])

            if max_delay >= 900000:
                ka = int(max_delay / 1000 * 1.5)
                new_cmds.insert(0, ASTFCmdKeepaliveMsg(ka))

        self._set_cmds(new_cmds)

    def _add_server_delay(self, cmds):
        rx_cmds = ('rx', 'rx_msg')
        tx_cmds = ('tx', 'tx_msg')
        last_rx_cmd = None
        new_cmds = []
        for cmd in cmds:
            curr_cmd = cmd.fields['name']
            if curr_cmd in rx_cmds: 
                last_rx_cmd = curr_cmd
            if curr_cmd in tx_cmds and last_rx_cmd == curr_cmd.replace('tx', 'rx'):
                new_cmds.append(self.s_delay)
                last_rx_cmd = None
            new_cmds.append(cmd)
        return new_cmds

    def set_tg_names(self, tg_names):
        self.tg_name_to_id = tg_names

    def __compile(self):
        # update offsets for  ASTFCmdJMPNZ
        # comvert var names to ids 

        i=0;
        for cmd in self.fields['commands']:
            if cmd.stream != None:
                if cmd.stream !=self.stream:
                    raise ASTFError(" Command %s stream mode is %s and different from the flow stream mode %s" % (cmd.fields['name'], cmd.stream, self.stream))

            if isinstance(cmd, ASTFCmdJMPBase):
                #print(" {0} {1}".format(self.__get_label_id(cmd.label),i));
                cmd.fields['offset']=self.__get_label_id(cmd.label)-(i);
                if 'id' in cmd.fields and isinstance(cmd.fields['id'],str):
                    if isinstance(cmd, ASTFCmdJMPDP):
                        cmd.fields['id']=self.__get_tick_var_index(cmd.fields['id'])
                    else:
                        cmd.fields['id']=self.__get_var_index(cmd.fields['id'])
            if isinstance(cmd, ASTFCmdSetValBase):
                id_name=cmd.fields['id']
                if isinstance(id_name,str):
                    cmd.fields['id']=self.__get_var_index(id_name)
            if isinstance(cmd, ASTFCmdSetTickValBase):
                id_name=cmd.fields['id']
                if isinstance(id_name,str):
                    cmd.fields['id']=self.__get_tick_var_index(id_name)
            if isinstance(cmd, ASTFCmdAddTickStats):
                id_name=cmd.fields['var_id']
                if isinstance(id_name,str):
                    cmd.fields['var_id']=self.__get_tick_var_index(id_name)
            if isinstance(cmd, ASTFCmdSetTemplate):
                id_name=cmd.fields['tg_id']
                if isinstance(id_name,str):
                    cmd.fields['tg_id']=self.tg_name_to_id[id_name]
            i=i+1


    def to_json(self):
        self.__compile()
        ret = {}
        ret['commands'] = []
        for cmd in self.fields['commands']:
            ret['commands'].append(cmd.to_json())
        if self.stream==False:
            ret['stream']=False
        if self.addon:
            ret['addon']=self.addon
        return ret

    def dump(self, out, var_name):
        out.write("cmd_list = []\n")
        for cmd in self.fields['commands']:
            out.write("cmd_list.append({0})\n".format(cmd.dump()))

        out.write("{0} = {1}()\n".format(var_name, self.__class__.__name__))
        out.write("{0}.set_cmds(cmd_list)\n".format(var_name))

    @property
    def payload_len(self):
        return self._p_len


class ASTFIPGenDist(object):
    """
        .. code-block:: python

            ip_gen_c = ASTFIPGenDist(ip_range=["16.0.0.0", "16.0.0.255"], distribution="seq")

    """

    class Inner(object):
        def __init__(self, ip_range, distribution="seq",per_core_distribution=None):
            self.fields = {}
            self.fields['ip_start'] = ip_range[0]
            self.fields['ip_end'] = ip_range[1]
            self.fields['distribution'] = distribution
            if per_core_distribution:
                self.fields['per_core_distribution']=per_core_distribution

        def __eq__(self, other):
            return self.fields == other.fields

        def is_overlaps(self, other_inner):
            my_start, my_end = ip2int(self.ip_start), ip2int(self.ip_end)
            other_start, other_end = ip2int(other_inner.ip_start), ip2int(other_inner.ip_end)

            return my_start <= other_end and my_end >= other_start 

        @property
        def ip_start(self):
            return self.fields['ip_start']

        @property
        def ip_end(self):
            return self.fields['ip_end']

        @property
        def distribution(self):
            return self.fields['distribution']

        @property
        def direction(self):
            return self.fields.get('dir')

        @direction.setter
        def direction(self, direction):
            self.fields['dir'] = direction

        @property
        def ip_offset(self):
            return self.fields['ip_offset']

        @ip_offset.setter
        def ip_offset(self, ip_offset):
            self.fields['ip_offset'] = ip_offset

        def to_json(self):
            return dict(self.fields)

    def __init__(self, ip_range, distribution="seq", per_core_distribution=None):

        """
        Define a ASTFIPGenDist


        :parameters:
                  ip_range  : list of  min-max ip strings

                  distribution  : string
                      "seq" or "rand"

                  per_core_distribution : "seq" or "default"
                     in case of "seq" each core will get continuous range of Ip. 
                     in case of "default" it is not necessarily the case.

        """

        ver_args = {"types":
                    [{"name": "ip_range", 'arg': ip_range, "t": "ip range", "must": True},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)
        distribution_vals = ["seq", "rand"]
        per_core_distribution_vals =  ["default", "seq"]
        if distribution not in distribution_vals:
            raise ASTFError("Distribution must be one of {0}".format(distribution_vals))
        if per_core_distribution:
            if per_core_distribution not in per_core_distribution_vals:
                raise ASTFError("per_core_distribution must be one of {0}".format(per_core_distribution_vals))

        new_inner = self.Inner(ip_range=ip_range, distribution=distribution,per_core_distribution=per_core_distribution)

        self.inner = new_inner
        self.index = None

    @property
    def ip_start(self):
        return self.inner.ip_start

    @property
    def ip_end(self):
        return self.inner.ip_end

    @property
    def distribution(self):
        return self.inner.distribution

    @property
    def direction(self):
        return self.inner.direction

    @direction.setter
    def direction(self, direction):
        self.inner.direction = direction

    @property
    def ip_offset(self):
        return self.inner.ip_offset

    @ip_offset.setter
    def ip_offset(self, ip_offset):
        self.inner.ip_offset = ip_offset

    def to_json(self):
        return {"index": self.index}


class ASTFIPGenGlobal(object):
    """
        .. code-block:: python

            ip_gen_c = ASTFIPGenGlobal(ip_offset="1.0.0.0")

    """

    def __init__(self, ip_offset="1.0.0.0", ip_offset_server=None):
        """
        Global properties for IP generator


        :parameters:
            ip_offset:
                | Offset for dual mask ports.
                | This value is added to each next pair of ports - ports 1 and 2 will have ip_offset added to IPs in their pool, ports 3 and 4 will have added ip_offset*2 and so on.

            ip_offset_server:
                set in case you want offset per side.
        """

        ver_args = {"types":
                    [{"name": "ip_offset", 'arg': ip_offset, "t": "ip address", "must": False},
                     {"name": "ip_offset_server", 'arg': ip_offset_server, "t": "ip address", "must": False},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)

        self.fields = {}
        self.fields['ip_offset'] = ip_offset
        if ip_offset_server:
            self.fields['ip_offset_server'] = ip_offset_server

    @property
    def ip_offset(self):
        return self.fields['ip_offset']

    @property
    def ip_offset_server(self):
        return self.fields.get('ip_offset_server', self.fields['ip_offset'])

    def to_json(self):
        return dict(self.fields)


class ASTFIPGen(object):
    """

        .. code-block:: python

            ip_gen_c = ASTFIPGenDist(ip_range=["16.0.0.0", "16.0.0.255"], distribution="seq")
            ip_gen_s = ASTFIPGenDist(ip_range=["48.0.0.0", "48.0.255.255"], distribution="seq")
            ip_gen = ASTFIPGen(glob=ASTFIPGenGlobal(ip_offset="1.0.0.0"),
                               dist_client=ip_gen_c,
                               dist_server=ip_gen_s)


    """

    def __init__(self, dist_client, dist_server, glob=ASTFIPGenGlobal()):
        """
        Define a ASTFIPGen generator


        :parameters:
                  dist_client  : Client side ASTFIPGenDist  :class:`trex.astf.trex_astf_profile.ASTFIPGenDist`

                  dist_server  : Server side ASTFIPGenDist  :class:`trex.astf.trex_astf_profile.ASTFIPGenDist`

                  glob :  ASTFIPGenGlobal see :class:`trex.astf.trex_astf_profile.ASTFIPGenGlobal`
        """

        ver_args = {"types":
                    [{"name": "glob", 'arg': glob, "t": ASTFIPGenGlobal, "must": False},
                     {"name": "dist_client", 'arg': dist_client, "t": ASTFIPGenDist, "must": True},
                     {"name": "dist_server", 'arg': dist_server, "t": ASTFIPGenDist, "must": True},
                     ]}

        ArgVerify.verify(self.__class__.__name__, ver_args)

        self.fields = {}
        self.fields['dist_client'] = dist_client
        if dist_client.direction and dist_client.direction != "c":
            raise ASTFError("dist_client.direction is already dir:{0}".format(dist_client.direction))
        dist_client.direction = "c"
        dist_client.ip_offset = glob.ip_offset
        self.fields['dist_server'] = dist_server
        if dist_server.direction and dist_server.direction != "s":
            raise ASTFError("dist_server.direction is already dir:{0}".format(dist_server.direction))
        dist_server.direction = "s"
        dist_server.ip_offset = glob.ip_offset_server

    @staticmethod
    def __str__():
        return "IPGen"

    def to_json(self):
        ret = {}
        for field in self.fields.keys():
            ret[field] = self.fields[field].to_json()

        return ret


# for future use
class ASTFCluster(object):
    def to_json(self):
        return {}


class ASTFTCPOptions(object):
    """
       .. code-block:: python

            opts = list of TCP option tuples (name, value)

    """

    def __init__(self, opts=None):
        self.fields = {}
        if opts is not None:
            for opt in opts:
                self.fields[opt[0]] = opt[1]

    @property
    def mss(self, val):
        return self.fields['MSS']

    @mss.setter
    def mss(self, val):
        self.fields['MSS'] = val

    def to_json(self):
        return dict(self.fields)

    def __eq__(self, other):
        if not other:
            return False
        if not hasattr(other, 'fields'):
            return False
        for key in self.fields.keys():
            if key not in other.fields:
                return False
            if self.fields[key] != other.fields[key]:
                return False
            return True



class ASTFAssociationRule(object):
    """

       .. code-block:: python

            # only `port`
            assoc=ASTFAssociationRule(port=81)

            # port with range or destination ips
            assoc=ASTFAssociationRule(port=81,ip_start="48.0.0.1",ip_end="48.0.0,16")

            # port with L7 content mapping rule
            assoc=ASTFAssociationRule(port=81,l7_map=[0,1,2,3])

            # port with L7 content mapping value (server-only mode)
            assoc=ASTFAssociationRule(port=81,l7_map={ "offset": [0,1], "value": [0,42] })


    """

    def __init__(self, port=80, ip_start=None, ip_end=None, l7_map=None, assoc_id=None):
        """

        :parameters:

            port: uint16_t
                destination port

            ip_start: string
                ip range start

            ip_end: string
                ip range end

            l7_map: list or dict
                L7 mapping content by byte offsets with optional masks and values

            assoc_id: uint64_t
                to specify a known value for the ASTFProgram addon handling


        """

        ver_args = {"types":
                    [{"name": "ip_start", 'arg': ip_start, "t": "ip address", "must": False},
                     {"name": "ip_end", 'arg': ip_end, "t": "ip address", "must": False},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)

        self.fields = {}
        self.fields['port'] = port
        if ip_start is not None:
            self.fields['ip_start'] = str(ip_start)
        if ip_end is not None:
            self.fields['ip_end'] = str(ip_end)

        if type(l7_map) is list or type(l7_map) is tuple:
            l7_map = { "offset": list(l7_map) }
        if type(l7_map) is dict:
            self.fields['l7_map'] = l7_map

        if assoc_id is not None:
            self.fields['assoc_id'] = assoc_id

    @property
    def port(self):
        return self.fields['port']

    def to_json(self):
        return dict(self.fields)


class ASTFAssociation(object):
    """
       .. code-block:: python

            assoc=ASTFAssociationRule(port=81)


    """
    def __init__(self, rules=ASTFAssociationRule()):
        """

        :parameters:

                  rules  : ASTFAssociationRule see :class:`trex.astf.trex_astf_profile.ASTFAssociationRule`
                       rule or rules list

        """

        ver_args = {"types":
                    [{"name": "rules", 'arg': rules, "t": ASTFAssociationRule, "must": False, "allow_list": True},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)

        self.rules = listify(rules)

    def to_json(self):
        ret = []
        for rule in self.rules:
            ret.append(rule.to_json())
        return ret

    @property
    def port(self):
        if len(self.rules) != 1:
            pass  # exception

        return self.rules[0].port

    def is_port_only(self):
        if len(self.rules) != 1:
            pass  # exception

        return len(self.rules[0].fields) == 1


class _ASTFTemplateBase(object):

    def __init__(self, program=None):
        self.fields = {}
        self.fields['program_index'] = None
        self.program = program
        self.is_stream = program.is_stream if program is not None else None


    def is_stream (self):
        return (self.is_stream)


    def to_json(self):
        ret = {}
        ret['program_index'] = self.fields['program_index']

        return ret


class _ASTFClientTemplate(_ASTFTemplateBase):
    def __init__(self, ip_gen, cluster=ASTFCluster(), program=None):
        super(_ASTFClientTemplate, self).__init__(program=program)
        self.fields['ip_gen'] = ip_gen
        self.fields['cluster'] = cluster

    def to_json(self):
        ret = super(_ASTFClientTemplate, self).to_json()
        ret['ip_gen'] = self.fields['ip_gen'].to_json()
        ret['cluster'] = self.fields['cluster'].to_json()
        return ret


class ASTFTCPClientTemplate(_ASTFClientTemplate):
    """
       One manual template

       .. code-block:: python

             client commands
            prog_c = ASTFProgram()
            prog_c.send(http_req)
            prog_c.recv(len(http_response))

            # ip generator
            ip_gen_c = ASTFIPGenDist(ip_range=["16.0.0.0", "16.0.0.255"], distribution="seq")
            ip_gen_s = ASTFIPGenDist(ip_range=["48.0.0.0", "48.0.255.255"], distribution="seq")
            ip_gen = ASTFIPGen(glob=ASTFIPGenGlobal(ip_offset="1.0.0.0"),
                               dist_client=ip_gen_c,
                               dist_server=ip_gen_s)

            # template
            temp_c = ASTFTCPClientTemplate(program=prog_c, ip_gen=ip_gen)  




     """

    def __init__(self, ip_gen, cluster=ASTFCluster(), program=None,
                 port=80, cps=1, glob_info=None,limit=None,cont=None,core_base=None):
        """

        :parameters:
                  
                  ip_gen  : ASTFIPGen see :class:`trex.astf.trex_astf_profile.ASTFIPGen`
                       generator

                  cluster :  ASTFCluster see :class:`trex.astf.trex_astf_profile.ASTFCluster`

                  program  : ASTFProgram see :class:`trex.astf.trex_astf_profile.ASTFProgram`
                        L7 emulation program

                  port     : uint16_t
                        destination port

                  cps      : float
                        New connection per second rate. Minimal value is 0.5

                  limit    : uint32_t 
                        limit the number of flows. default is None which means zero (there is no limit)

                  cont     : bool
                        try to keep the number of flows up to limit.

                  core_base : uint16_t
                        preferred core base hint when limit value is less than the number of cores.
                        default is pseudo random value.

                  glob_info : ASTFGlobalInfoPerTemplate see :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfoPerTemplate`
        """

        ver_args = {"types":
                    [{"name": "ip_gen", 'arg': ip_gen, "t": ASTFIPGen},
                     {"name": "cluster", 'arg': cluster, "t": ASTFCluster, "must": False},
                     {"name": "limit", 'arg': limit, "t": int, "must": False},
                     {"name": "cont", 'arg': cont, "t": bool, "must": False},
                     {"name": "core_base", 'arg': core_base, "t": int, "must": False},
                     {"name": "glob_info", 'arg': glob_info, "t": ASTFGlobalInfoPerTemplate, "must": False},
                     {"name": "program", 'arg': program, "t": ASTFProgram}]
                    }
        ArgVerify.verify(self.__class__.__name__, ver_args)

        super(ASTFTCPClientTemplate, self).__init__(ip_gen=ip_gen, cluster=cluster, program=program)
        self.fields['port'] = port
        if cps:
            self.fields['cps'] = cps
        self.fields['glob_info'] = glob_info
        if limit:
            self.fields['limit'] = limit
            if cont:
                self.fields['cont'] = cont
            if core_base:
                self.fields['core_base'] = core_base

    def to_json(self):
        ret = super(ASTFTCPClientTemplate, self).to_json()
        ret['port'] = self.fields['port']
        if 'cps' in self.fields:
            ret['cps'] = self.fields['cps']
        if 'limit' in self.fields:
            ret['limit'] = self.fields['limit']
            if 'cont' in self.fields:
                ret['cont'] = self.fields['cont']

        if self.fields['glob_info'] is not None:
            ret['glob_info'] = self.fields['glob_info'].to_json()
        return ret


class ASTFTCPServerTemplate(_ASTFTemplateBase):
    """
       One server side template

       .. code-block:: python

            # server commands
            prog_s = ASTFProgram()
            prog_s.recv(len(http_req))
            prog_s.send(http_response)


            # template
            temp_s = ASTFTCPServerTemplate(program=prog_s, tcp_info=tcp_params)  # using default association

     """

    def __init__(self, program=None, assoc=ASTFAssociation(), glob_info=None):
        """

        :parameters:

                  program  : ASTFProgram see :class:`trex.astf.trex_astf_profile.ASTFProgram`
                        L7 emulation program

                  glob_info : ASTFGlobalInfoPerTemplate see :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfoPerTemplate`

                  assoc    : ASTFAssociation see :class:`trex.astf.trex_astf_profile.ASTFAssociation`

        """
        ver_args = {"types":
                     [
                     {"name": "assoc", 'arg': assoc, "t": [ASTFAssociation, ASTFAssociationRule], "must": False},
                     {"name": "glob_info", 'arg': glob_info, "t": ASTFGlobalInfoPerTemplate, "must": False},
                     {"name": "program", 'arg': program, "t": ASTFProgram}
                     ]
                    }
        ArgVerify.verify(self.__class__.__name__, ver_args)

        super(ASTFTCPServerTemplate, self).__init__(program=program)
        if isinstance(assoc, ASTFAssociationRule):
            new_assoc = ASTFAssociation(rules=assoc)
            self.fields['assoc'] = new_assoc
        else:
            self.fields['assoc'] = assoc
        self.fields['glob_info'] = glob_info

    def to_json(self):
        ret = super(ASTFTCPServerTemplate, self).to_json()
        ret['assoc'] = self.fields['assoc'].to_json()
        if self.fields['glob_info'] is not None:
            ret['glob_info'] = self.fields['glob_info'].to_json()
        return ret


class ASTFCapInfo(object):
    """

        .. code-block:: python

            ASTFCapInfo(file="../avl/delay_10_http_browsing_0.pcap",cps=1)

            ASTFCapInfo(file="../avl/delay_10_http_browsing_0.pcap",l7_percent=10.0)

            ASTFCapInfo(file="../avl/delay_10_http_browsing_0.pcap",l7_percent=10.0,port=8080)

            ASTFCapInfo(file="../avl/delay_10_http_browsing_0.pcap",l7_percent=10.0,port=8080,ip_gen=Mygen)

    """

    def __init__(self, file=None, cps=None, assoc=None, ip_gen=None, port=None, l7_percent=None,
                 s_glob_info=None, c_glob_info=None,limit=None, cont=None, tg_name=None, s_delay=None, udp_mtu=None):
        """
        Define one template information based on pcap file analysis

        :parameters:
                  file  : string
                      pcap file name. Filesystem directory location is relative to the profile file in case it is not start with /

                  cps  :  float
                       new connection per second rate

                  assoc :  ASTFAssociation see :class:`trex.astf.trex_astf_profile.ASTFAssociation`
                       rule for server association in default take the destination port from pcap file

                  ip_gen  : ASTFIPGen see :class:`trex.astf.trex_astf_profile.ASTFIPGen`
                      tuple generator for this template

                  port    : uint16_t
                      Override destination port, by default is taken from pcap

                  l7_percent :  float
                        L7 stream bandwidth percent

                  limit     : uint32_t 
                        Limit the number of flows 

                  cont     : bool
                        try to keep the number of flows up to limit.

                  s_glob_info : ASTFGlobalInfoPerTemplate see :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfoPerTemplate`

                  c_glob_info : ASTFGlobalInfoPerTemplate see :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfoPerTemplate`

                  tg_names : string or None
                        All the templates within the tg_name (template group name) will have shared statistics. 
                        All the templates that haven't defined tg_name are collected under the same group.

                  s_delay : ASTFCmdDelay or ASTFCmdDelayRnd see :class:`trex.astf.trex_astf_profile.ASTFCmdDelay` and :class:`trex.astf.trex_astf_profile.ASTFCmdDelayRnd`
                      Server delay command before sending response back to client. defaults to None means no delay.
                  
                  udp_mtu: int or None
                      MTU for udp packets, if packets exceeding the specified value they will be cut down from L7 in order to fit. defaults to None.
        
        """

        ver_args = {"types":
                    [{"name": "file", 'arg': file, "t": str},
                     {"name": "assoc", 'arg': assoc, "t": [ASTFAssociation, ASTFAssociationRule], "must": False},
                     {"name": "ip_gen", 'arg': ip_gen, "t": ASTFIPGen, "must": False},
                     {"name": "c_glob_info", 'arg': c_glob_info, "t": ASTFGlobalInfoPerTemplate, "must": False},
                     {"name": "limit", 'arg': limit, "t": int, "must": False},
                     {"name": "cont", 'arg': cont, "t": bool, "must": False},
                     {"name": "s_glob_info", 'arg': s_glob_info, "t": ASTFGlobalInfoPerTemplate, "must": False},
                     {"name": "tg_name", 'arg': tg_name, "t": str, "must": False},
                     {"name": "s_delay", 'arg': s_delay, "t": [ASTFCmdDelay, ASTFCmdDelayRnd], "must": False},
                     {"name": "udp_mtu", 'arg': udp_mtu, "t": int, "must": False},
                     ]}
        ArgVerify.verify(self.__class__.__name__, ver_args)

        if l7_percent is not None:
            if cps is not None:
                raise ASTFErrorBadParamCombination(self.__class__.__name__, "cps", "l7_percent")
            self.l7_percent = l7_percent
            self.cps = None
        else:
            if cps is not None:
                self.cps = cps
            else:
                self.cps = 1
            self.l7_percent = None

        self.file = file
        if assoc is not None:
            if port is not None:
                raise ASTFErrorBadParamCombination(self.__class__.__name__, "port", "assoc")
            if type(assoc) is ASTFAssociationRule:
                self.assoc = ASTFAssociation(assoc)
            else:
                self.assoc = assoc
        else:
            if port is not None:
                self.assoc = ASTFAssociation(ASTFAssociationRule(port=port))
            else:
                self.assoc = None
        
        if tg_name is not None:
            if len(tg_name) > 20 or len(tg_name) == 0:
                raise ASTFError("tg_name is empty or too long")
        
        self.ip_gen = ip_gen
        self.c_glob_info = c_glob_info
        self.s_glob_info = s_glob_info
        self.limit = limit
        self.cont = cont
        self.tg_name = tg_name
        self.s_delay = s_delay
        self.udp_mtu = udp_mtu

class ASTFTemplate(object):
    """
       One manual template

       .. code-block:: python

            # client commands
            prog_c = ASTFProgram()
            prog_c.send(http_req)
            prog_c.recv(len(http_response))

            prog_s = ASTFProgram()
            prog_s.recv(len(http_req))
            prog_s.send(http_response)

            # ip generator
            ip_gen_c = ASTFIPGenDist(ip_range=["16.0.0.0", "16.0.0.255"], distribution="seq")
            ip_gen_s = ASTFIPGenDist(ip_range=["48.0.0.0", "48.0.255.255"], distribution="seq")
            ip_gen = ASTFIPGen(glob=ASTFIPGenGlobal(ip_offset="1.0.0.0"),
                               dist_client=ip_gen_c,
                               dist_server=ip_gen_s)


            # template
            temp_c = ASTFTCPClientTemplate(program=prog_c,ip_gen=ip_gen)
            temp_s = ASTFTCPServerTemplate(program=prog_s)  # using default association
            template = ASTFTemplate(client_template=temp_c, server_template=temp_s)

     """

    def __init__(self, client_template=None, server_template=None, tg_name=None):
        """
        Define a ASTF profile

        You should give either templates or cap_list (mutual exclusion).

        :parameters:
                  client_template  : ASTFTCPClientTemplate see :class:`trex.astf.trex_astf_profile.ASTFTCPClientTemplate`
                       client side template info

                  server_template  :  ASTFTCPServerTemplate see :class:`trex.astf.trex_astf_profile.ASTFTCPServerTemplate`
                       server side template info

                  tg_name          : string or None
                        All the templates within the tg_name (template group name) will have shared statistics. 
                        All the templates that haven't defined tg_name are collected under the same group.
        """
        ver_args = {"types":
                    [{"name": "client_template", 'arg': client_template, "t": ASTFTCPClientTemplate},
                     {"name": "server_template", 'arg': server_template, "t": ASTFTCPServerTemplate},
                     {"name": "tg_name", 'arg': tg_name, "t": str, "must": False}]
                    }
        ArgVerify.verify(self.__class__.__name__, ver_args)

        if client_template.is_stream() != server_template.is_stream() :
            raise ASTFError(" Client template stream mode is {0} and different from server template mode {1}".format( client_template.is_stream(), server_template.is_stream() ) )

        if tg_name is not None:
            if len(tg_name) > 20 or len(tg_name) == 0:
                raise ASTFError("tg_name is empty or too long")

        self.tg_name = tg_name
        self.fields = {}
        self.fields['client_template'] = client_template
        self.fields['server_template'] = server_template


    def to_json(self):
        ret = {}
        for field in self.fields.keys():
            if field != 'tg_id':
                ret[field] = self.fields[field].to_json()
            elif self.fields['tg_id'] != 0:
                ret['tg_id'] = self.fields['tg_id']

        return ret

class _ASTFTCPInfo(object):
    def __init__(self, file=None):
        if file is not None:
            cap = pcap_reader(_ASTFCapPath.get_pcap_file_path(file))
            cap.analyze()
            new_port = cap.d_port

        self.m_port = new_port

    @property
    def port(self):
        return self.m_port

class ASTFProfileLight(object):
    """ ASTF profile light to save the json dict """
    def __init__(self, json_dict):
        if not (type(json_dict) is dict):
            raise TRexError("json_dict should be dict type")

        self.json_dict = json_dict;

    def to_json(self):
        return (self.json_dict);

    def to_json_str(self):
        ret = self.to_json()
        return json.dumps(ret, indent=4, separators=(',', ': '))

    def print_stats(self):
        print(" NOT supported for this format \n");


class ASTFProfile(object):
    """ ASTF profile

       .. code-block:: python

            ip_gen_c = ASTFIPGenDist(ip_range=["16.0.0.0", "16.0.0.255"], distribution="seq")
            ip_gen_s = ASTFIPGenDist(ip_range=["48.0.0.0", "48.0.255.255"], distribution="seq")
            ip_gen = ASTFIPGen(glob=ASTFIPGenGlobal(ip_offset="1.0.0.0"),
                               dist_client=ip_gen_c,
                               dist_server=ip_gen_s)

            return ASTFProfile(default_ip_gen=ip_gen,
                                cap_list=[ASTFCapInfo(file="../avl/delay_10_http_browsing_0.pcap",cps=1)])

    """

    def __init__(self, default_ip_gen, default_c_glob_info=None, default_s_glob_info=None,
                 templates=None, cap_list=None, s_delay=None, udp_mtu=None):
        """
        Define a ASTF profile

        You should give at least a template or a cap_list, maybe both.

        :parameters:
                  default_ip_gen  : ASTFIPGen  :class:`trex.astf.trex_astf_profile.ASTFIPGen`
                       tuple generator object

                  default_c_glob_info  :  ASTFGlobalInfo :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfo`
                       tcp parameters to be used for client side, if cap_list is given. This is optional. If not specified,
                       TCP parameters for each flow will be taken from its cap file.

                  default_s_glob_info  :  ASTFGlobalInfo :class:`trex.astf.trex_astf_global_info.ASTFGlobalInfo`
                       Same as default_tcp_server_info for client side.

                  templates  :  ASTFTemplate see :class:`trex.astf.trex_astf_profile.ASTFTemplate`
                       define a list of manual templates or one template

                  cap_list  : ASTFCapInfo see :class:`trex.astf.trex_astf_profile.ASTFCapInfo`
                      define a list of pcap files list in case there is no templates

                  s_delay : ASTFCmdDelay or ASTFCmdDelayRnd see :class:`trex.astf.trex_astf_profile.ASTFCmdDelay` and :class:`trex.astf.trex_astf_profile.ASTFCmdDelayRnd`
                      Server delay command before sending response back to client.
                      This will be applied on all cap in cap list, unless cap specified his own s_delay. defaults to None means no delay.
                  
                  udp_mtu: int or None
                      MTU for udp packets, if packets exceeding the specified value they will be cut down from L7 in order to fit.
                      This will be applied on all cap in cap list, unless cap specified his own udp_mtu. defaults to None.
        """

        ver_args = {"types":
                    [{"name": "templates", 'arg': templates, "t": ASTFTemplate, "allow_list": True, "must": False},
                     {"name": "cap_list", 'arg': cap_list, "t": ASTFCapInfo, "allow_list": True, "must": False},
                     {"name": "default_ip_gen", 'arg': default_ip_gen, "t": ASTFIPGen},
                     {"name": "default_c_glob_info", 'arg': default_c_glob_info, "t": ASTFGlobalInfo, "must": False},
                     {"name": "default_s_glob_info", 'arg': default_s_glob_info, "t": ASTFGlobalInfo, "must": False},
                    {"name": "s_delay", 'arg': s_delay, "t": [ASTFCmdDelay, ASTFCmdDelayRnd], "must": False},
                    {"name": "udp_mtu", 'arg': udp_mtu, "t": int, "must": False},]
                    }
        ArgVerify.verify(self.__class__.__name__, ver_args)

        self.default_c_glob_info = default_c_glob_info
        self.default_s_glob_info = default_s_glob_info
        self.templates = []
        self.tg_name_to_id = collections.OrderedDict()
        self.cache = ASTFProfileCache(profile = self)

        if (templates is None) and (cap_list is None):
             raise ASTFErrorBadParamCombination(self.__class__.__name__, "templates", "cap_list")

        if cap_list is not None:
            self.cap_list = listify(cap_list)

        if templates is not None:
            self.templates = listify(templates)
            for template in self.templates:
                self._add_tg_id_to_template(template)
            server_ports = []
            for template in self.templates:
                port = template.fields['server_template'].fields['assoc'].port
                if not template.fields['server_template'].fields['assoc'].is_port_only():
                    # if assoc is limited by ip range or L7 mapping, it would be checked by server.
                    pass
                elif port in server_ports:
                    raise ASTFError("Two server template with port {}".format(port))
                else:
                    server_ports.append(port)

        if cap_list is not None:
            mode = None
            all_cap_info = []
            d_ports = {}
            total_payload = 0
            for cap in self.cap_list:
                cap_file = cap.file
                ip_gen = cap.ip_gen if cap.ip_gen is not None else default_ip_gen
                glob_c = cap.c_glob_info
                glob_s = cap.s_glob_info
                cap_udp_mtu = cap.udp_mtu if cap.udp_mtu is not None else udp_mtu
                prog_c = ASTFProgram(file=cap_file, side="c", udp_mtu = cap_udp_mtu)
                server_delay = cap.s_delay if cap.s_delay is not None else s_delay
                prog_s = ASTFProgram(file=cap_file, side="s", udp_mtu = cap_udp_mtu, s_delay=server_delay)
                prog_c.update_keepalive(prog_s)
                if not prog_c.stream:
                    # update client's keepalive if udp
                    prog_s.update_keepalive(prog_c)

                tcp_c = _ASTFTCPInfo(file=cap_file)
                tcp_c_port = tcp_c.port

                cps = cap.cps
                l7_percent = cap.l7_percent
                if mode is None:
                    if l7_percent is not None:
                        mode = "l7_percent"
                    else:
                        mode = "cps"
                else:
                    if mode == "l7_percent" and l7_percent is None:
                        raise ASTFError("If one cap specifies l7_percent, then all should specify it")
                    if mode == "cps" and l7_percent is not None:
                        raise ASTFError("Can't mix specifications of cps and l7_percent in same cap list")

                total_payload += prog_c.payload_len
                if cap.assoc is None:
                    d_port = tcp_c_port
                    my_assoc = ASTFAssociation(rules=ASTFAssociationRule(port=d_port))
                else:
                    d_port = cap.assoc.port
                    my_assoc = cap.assoc
                if not my_assoc.is_port_only():
                    # if assoc is limited by ip range or L7 mapping, it would be checked by server.
                    pass
                elif d_port in d_ports:
                    raise ASTFError("More than one cap use dest port %s. This is currently not supported. Files with same port: %s, %s" % (d_port, d_ports[d_port], cap_file))
                else:
                    d_ports[d_port] = cap_file

                all_cap_info.append({"ip_gen": ip_gen, "prog_c": prog_c, "prog_s": prog_s, "glob_c": glob_c, "glob_s": glob_s,
                                     "cps": cps, "l7_percent": l7_percent, "d_port": d_port, "my_assoc": my_assoc,"limit":cap.limit, "cont":cap.cont, "tg_name": cap.tg_name})
            # calculate cps from l7 percent
            # first know how much percent it represents from the trafic
            # 100              |    ?
            # total_payload    |   payload_len
            #
            # trafic percent = payload * 100 / total_payload
            #
            # then go from actual trafic percent to expected trafic percent
            #
            # 1 cps         | trafic percent
            #  ? cps        | expected_percent
            #
            # final_cps = expected_percent / trafic_percent
            if mode == "l7_percent":
                lowest = 1
                percent_sum = 0
                for c in all_cap_info:
                    payload_percent = c["prog_c"].payload_len * 100.0 / total_payload


                    # the 10 here is because Trex doesnt like CPS under 0.5
                    # so we try to go up an order of magnitude
                    # since most users will just multiply this again with the global multiplier after
                    target_cps = c["l7_percent"] / payload_percent

                    c["cps"] = target_cps

                    if target_cps < lowest:
                        lowest = target_cps
                    percent_sum += c["l7_percent"]
                if percent_sum != 100:
                    raise ASTFError("l7_percent values must sum up to 100")
                # normalize it all so that lowest = 1
                mult = 1 / lowest
                for c in all_cap_info:
                    c["cps"] = c["cps"] * mult


            for c in all_cap_info:
                temp_c = ASTFTCPClientTemplate(program=c["prog_c"], glob_info=c["glob_c"], ip_gen=c["ip_gen"], port=c["d_port"],
                                               cps=c["cps"],limit=c["limit"],cont=c["cont"])
                temp_s = ASTFTCPServerTemplate(program=c["prog_s"], glob_info=c["glob_s"], assoc=c["my_assoc"])
                template = ASTFTemplate(client_template=temp_c, server_template=temp_s, tg_name=c["tg_name"])
                self._add_tg_id_to_template(template)
                self.templates.append(template)

    def _add_tg_id_to_template(self, template):
        if template.tg_name in self.tg_name_to_id:
            template.fields['tg_id'] = self.tg_name_to_id[template.tg_name]
        else:
            if template.tg_name is None:
                template.fields['tg_id'] = 0
            if template.tg_name:
                template.fields['tg_id'] = len(self.tg_name_to_id) + 1
                self.tg_name_to_id[template.tg_name] = len(self.tg_name_to_id) + 1

    def to_json_str(self, pretty = True, sort_keys = False):
        data = self.to_json()
        if pretty:
            return json.dumps(data, indent=4, separators=(',', ': '), sort_keys = sort_keys)
        return json.dumps(data, sort_keys = sort_keys)

    @pretty_exceptions
    def to_json(self):
        self.cache.fill_cache()
        ret = {}
        ret['buf_list'] = self.cache.program_cache.to_json()
        ret['ip_gen_dist_list'] = self.cache.gen_dist_cache.to_json()
        ret['program_list'] = self.cache.template_cache.to_json()
        if self.default_c_glob_info is not None:
            ret['c_glob_info'] = self.default_c_glob_info.to_json()
        if self.default_s_glob_info is not None:
            ret['s_glob_info'] = self.default_s_glob_info.to_json()
        ret['templates'] = []
        for t in self.templates:
            ret['templates'].append(t.to_json())
        ret['tg_names'] = list(self.tg_name_to_id.keys())
        # Remember! If tg_name = None then tg_id = 0 and tg_name is not passed to the server. As such
        # when parsing the JSON in the server be careful to pay attention that the first tg_name belongs to
        # tg_id = 1.
        return ret;

    @pretty_exceptions
    def print_stats(self):
        self.cache.fill_cache()
        tot_bps = 0
        tot_cps = 0
        print ("Num buffers: {0}".format(self.cache.program_cache.get_len()))
        print ("Num programs: {0}".format(self.cache.template_cache.num_programs()))
        for i in range(0, len(self.templates)):
            print ("template {0}:".format(i))
            d = self.templates[i].to_json()
            c_prog_ind = d['client_template']['program_index']
            s_prog_ind = d['server_template']['program_index']
            tot_bytes = self.cache.template_cache.get_total_send_bytes(c_prog_ind) + self.cache.template_cache.get_total_send_bytes(s_prog_ind)
            temp_cps = d['client_template']['cps']
            temp_bps = tot_bytes * temp_cps * 8
            print ("  total bytes:{0} cps:{1} bps(bytes * cps * 8):{2}".format(tot_bytes, temp_cps, temp_bps))
            tot_bps += temp_bps
            tot_cps += temp_cps
        print("total for all templates - cps:{0} bps:{1}".format(tot_cps, tot_bps))

    def clear_cache(self):
        self.cache.clear_all()

    @staticmethod
    def get_module_tunables(module):
        # remove self and variables
        func = module.register().get_profile
        argc = func.__code__.co_argcount
        tunables = func.__code__.co_varnames[1:argc]

        # fetch defaults
        defaults = func.__defaults__
        if defaults is None:
            return {}
        if len(defaults) != (argc - 1):
            raise TRexError("Module should provide default values for all arguments on get_streams()")

        output = {}
        for t, d in zip(tunables, defaults):
            output[t] = d

        return output

    @classmethod
    @pretty_exceptions
    def load_py (cls, python_file, **kwargs):
        """ Load from ASTF Python profile """

        # in case load_py is not being called from astf_client, there is need to convert
        # the tunables to the new format to support argparse. 
        if "tunables" not in kwargs:
            tunable_list = []
            # converting from tunables dictionary to list 
            for tunable_key in kwargs:
                tunable_list.extend(["--{}".format(tunable_key), str(kwargs[tunable_key])])
            kwargs["tunables"] = tunable_list

        # check filename
        if not os.path.isfile(python_file):
            raise TRexError("File '{0}' does not exist".format(python_file))

        basedir = os.path.dirname(python_file)
        sys.path.insert(0, basedir)

        try:
            file    = os.path.basename(python_file).split('.')[0]
            module = __import__(file, globals(), locals(), [], 0)
            imp.reload(module) # reload the update 

            t = cls.get_module_tunables(module)

            profile = module.register().get_profile(**kwargs)

            profile.meta = {'type': 'python',
                            'tunables': t}
            return profile
        except SystemExit:
                # called ".. -t --help", return None
            return None
        finally:
            sys.path.remove(basedir)



    @staticmethod
    def load_json (json_file):
        """ Load (from JSON file) a profile with a number of streams """
                # check filename
        if not os.path.isfile(json_file):
            raise TRexError("file '{0}' does not exists".format(json_file))

        # read the content
        with open(json_file) as f:
            try:
                data = json.load(f)
                profile =  ASTFProfileLight(data)
                
            except (ValueError, yaml.parser.ParserError):
                raise TRexError("file '{0}' is not a valid {1} formatted file".format(plain_file, 'JSON'))
            
        return profile




    @classmethod
    def load(cls, filename, **kwargs):
        """ Load a profile by its type. Supported types are: 
           * py
           * json

           :Parameters:
              filename  : string as filename 
              kwargs    : forward those key-value pairs to the profile

        """

        x = os.path.basename(filename).split('.')
        suffix = x[1] if (len(x) == 2) else None

        if suffix == 'py':
            profile = cls.load_py(filename, **kwargs)

        elif suffix == 'json':
            profile = cls.load_json(filename)
        else:
            raise TRexError("unknown profile file type: '{0}'".format(suffix))

        return profile

class ASTFProfileCache(object):
    """ Cache for ASTFProfile, using 3 caches: ASTFIPGenDistCache, ASTFProgramCache and ASTFTemplateCache.
    Every ASTFProfile has a unique cache in order to prevent collisions """

    def __init__(self, profile):
        self.gen_dist_cache = ASTFIPGenDistCache()
        self.program_cache = ASTFProgramCache()
        self.template_cache = ASTFTemplateCache()
        self.profile = profile

    def clear_all(self):
        self.gen_dist_cache = ASTFIPGenDistCache()
        self.program_cache = ASTFProgramCache()
        self.template_cache = ASTFTemplateCache()

    def fill_cache(self):
        """ Clear the cache and fill it back using self.profile, iterating through all profile templates """
        self.clear_all()

        for template in self.profile.templates:
            client_template = template.fields['client_template']
            server_template = template.fields['server_template']
            tcp_templates = [client_template, server_template]

            for tcp_template in tcp_templates:
                tcp_template.program.set_tg_names(self.profile.tg_name_to_id)
                self.program_cache.add_commands_from_program(tcp_template.program)
                self.template_cache.add_program_from_template(tcp_template)

            ip_gen = client_template.fields['ip_gen']
            self.gen_dist_cache.add_inner(ip_gen)

class ASTFIPGenDistCache(object):
    """ Cache all the IP generator inners """
    def __init__(self):
        self.in_list = []

    def clear_cache(self):
        self.in_list = []

    def to_json(self):
        ret = []
        for gen_dst in self.in_list:
            ret.append(gen_dst.to_json())
        return ret

    def add_inner(self, ip_gen):
        ip_dest_client = ip_gen.fields['dist_client']
        ip_dest_server = ip_gen.fields['dist_server']

        self._add_inner(ip_dest_client, is_client = True)
        self._add_inner(ip_dest_server, is_client = False)

    def _add_inner(self, ip_gen_dist, is_client):
        new_inner = ip_gen_dist.inner
        overlap_inner = None

        for i, inner in enumerate(self.in_list):

            if new_inner == inner:
                ip_gen_dist.index = i
                ip_gen_dist.inner = inner  # reference the inner in cache in order to del the duplicate
                return
            elif is_client and inner.is_overlaps(new_inner):
                overlap_inner = inner

        if overlap_inner is not None:
            raise ASTFErrorOverlapIP([new_inner.ip_start, new_inner.ip_end], [overlap_inner.ip_start, overlap_inner.ip_end])

        self.in_list.append(new_inner)
        ip_gen_dist.index = len(self.in_list) - 1

class ASTFProgramCache(object):
    """ Cache all the commands from all ASTFPrograms """

    @staticmethod
    def commands_hash(cmd):
        return cmd.buf if type(cmd.buf) is not dict else tuple(cmd.buf.items())

    def __init__(self):
        self.buf_list = BufferList(hash_function = ASTFProgramCache.commands_hash)

    def get_len(self):
        return self.buf_list.get_len()

    def clear_cache(self):
        self.buf_list = BufferList(hash_function = ASTFProgramCache.commands_hash)

    def to_json(self):
        return self.buf_list.to_json()

    def add_commands_from_program(self, program):
        commands = program.fields['commands']
        for cmd in commands:
            if cmd.buffer:
                cmd.index = self.buf_list.add(cmd)

class ASTFTemplateCache(object):
    """ Cache all the programs in ASTFTemplate """

    @staticmethod
    def programs_hash(program):
        return hashlib.sha256(repr(program.to_json()).encode()).digest()

    def __init__(self):
        self.programs = BufferList(hash_function = ASTFTemplateCache.programs_hash)

    def clear_cache(self):
        self.programs = BufferList(hash_function = ASTFTemplateCache.programs_hash)

    def to_json(self):
        ret = []
        for program in self.programs.buf_list:
            ret.append(program.to_json())
        return ret

    def get_total_send_bytes(self, ind):
        return self.programs.buf_list[ind].total_send_bytes

    def num_programs(self):
        return self.programs.get_len()

    def add_program_from_template(self, template):
        template.fields['program_index'] = self.programs.add(template.program)

class BufferList(object):
    """ Cache implementation for ASTFTemplateCache and ASTFProgramCache, using a different hash function supplied in __init__ """

    def __init__(self, hash_function):
        self.buf_list = []
        self.buf_hash = {}
        self.hash_function = hash_function

    def get_len(self):
        return len(self.buf_list)

    # add, and return index of added buffer
    def add(self, new_buf):

        m = self.hash_function(new_buf)
        if m in self.buf_hash:            
            return self.buf_hash[m]
        else:
            if hasattr(new_buf, 'buf'):
                # new_buf is a command
                self.buf_list.append(new_buf.buf)
            else:
                # new_buf is a program
                self.buf_list.append(new_buf)
            new_index = len(self.buf_list) - 1
            self.buf_hash[m] = new_index
            return new_index

    def to_json(self):
        return self.buf_list
