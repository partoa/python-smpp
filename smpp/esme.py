import socket

from pdu_builder import *
import logging

class StateError(Exception):
    pass

class ESME(object):

    def __init__(self):
        self.state = 'CLOSED'
        self.sequence_number = 1
        self.conn = None
        self.defaults = {
                'host':'127.0.0.1',
                'port':2775,
                'dest_addr_ton':0,
                'dest_addr_npi':0,
                }
        self.logger = logging.getLogger('smpp.esme')

    def loadDefaults(self, defaults):
        self.defaults = dict(self.defaults, **defaults)


    def connect(self):
        if self.state in ['CLOSED']:
            self.logger.info('connect')
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.defaults['host'], self.defaults['port']))
            self.state = 'OPEN'


    def disconnect(self):
        if self.state in ['BOUND_TX', 'BOUND_RX', 'BOUND_TRX']:
            self.logger.info('disconnect')
            self._unbind()
        if self.state in ['OPEN']:
            self.logger.info('close connection')
            self.conn.close()
            self.state = 'CLOSED'


    def _recv(self):
        pdu = None
        length_bin = self.conn.recv(4)
        if not length_bin:
            return None
        else:
            if len(length_bin) == 4:
                length = int(binascii.b2a_hex(length_bin),16)
                rest_bin = self.conn.recv(length-4)
                pdu = to_object(unpack_pdu(length_bin + rest_bin))
                self.logger.debug('received %r', pdu)
            return pdu


    def _is_ok(self, pdu, id_check=None):
        if isinstance(pdu, PDU):
            pdu = pdu.get_obj()
        if isinstance(pdu, dict) \
               and pdu.get('header',{}).get('command_status') == 'ESME_ROK' \
               and (id_check == None
                    or id_check == pdu['header'].get('command_id'))):
            return True
        else:
            return False


    def bind_transmitter(self):
        if self.state in ['CLOSED']:
            self.connect()
        if self.state in ['OPEN']:
            pdu = BindTransmitter(self.sequence_number, **self.defaults)
            self.conn.send(pdu.get_bin())
            self.sequence_number +=1
            if self._is_ok(self._recv(), 'bind_transmitter_resp'):
                self.state = 'BOUND_TX'


    def _unbind(self):
        if self.state in ['BOUND_TX', 'BOUND_RX', 'BOUND_TRX']:
            pdu = Unbind(self.sequence_number)
            self.conn.send(pdu.get_bin())
            self.sequence_number +=1
            if self._is_ok(self._recv(), 'unbind_resp'):
                self.state = 'OPEN'


    def submit_sm(self, **kwargs):
        if self.state in ['BOUND_TX', 'BOUND_TRX']:
            self.logger.info('submit_sm %s', dict(self.defaults, **kwargs))
            pdu = SubmitSM(self.sequence_number, **dict(self.defaults, **kwargs))
            self.conn.send(pdu.get_bin())
            self.sequence_number +=1
            submit_sm_resp = self._recv()
            #print self._is_ok(submit_sm_resp, 'submit_sm_resp')
        else:
            raise StateError('cannot submit sm in state %s', self.state)


    def submit_multi(self, dest_address=[], **kwargs):
        if self.state in ['BOUND_TX', 'BOUND_TRX']:
            pdu = SubmitMulti(self.sequence_number, **dict(self.defaults, **kwargs))
            for item in dest_address:
                if isinstance(item, str): # assume strings are addresses not lists
                    pdu.addDestinationAddress(
                            item,
                            dest_addr_ton = self.defaults['dest_addr_ton'],
                            dest_addr_npi = self.defaults['dest_addr_npi'],
                            )
                elif isinstance(item, dict):
                    if item.get('dest_flag') == 1:
                        pdu.addDestinationAddress(
                                item.get('destination_addr', ''),
                                dest_addr_ton = item.get('dest_addr_ton',
                                    self.defaults['dest_addr_ton']),
                                dest_addr_npi = item.get('dest_addr_npi',
                                    self.defaults['dest_addr_npi']),
                                )
                    elif item.get('dest_flag') == 2:
                        pdu.addDistributionList(item.get('dl_name'))
            self.conn.send(pdu.get_bin())
            self.sequence_number +=1
            submit_multi_resp = self._recv()
            #print self._is_ok(submit_multi_resp, 'submit_multi_resp')
        else:
            raise StateError('cannot submit multi sm in state %s', self.state)


