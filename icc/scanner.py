#!/usr/local/bin/python2
# -*- coding: utf-8 -*-
# @file
# @author Piotr Krysik <ptrkrysik@gmail.com>
# @author Roman Khassraf <rkhassraf@gmail.com>
# @section LICENSE
#
# Gr-gsm is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# Gr-gsm is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gr-gsm; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
#
from gnuradio import blocks
from gnuradio import gr
from gnuradio import eng_notation
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from gnuradio.filter import pfb
from math import pi
from optparse import OptionParser

import grgsm
import numpy
import os
import osmosdr
import pmt
import time

from aux import ChannelInfo

#from wideband_receiver import *

class receiver_with_decoder(grgsm.hier_block):

    def __init__(self, OSR=4, chan_num=0, fc=939.4e6, ppm=0, samp_rate=0.2e6):
        grgsm.hier_block.__init__(
            self, "Receiver With Decoder",
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),
            gr.io_signature(0, 0, 0),
        )
        self.message_port_register_hier_out("bursts")
        self.message_port_register_hier_out("msgs")

        ##################################################
        # Parameters
        ##################################################
        self.OSR = OSR
        self.chan_num = chan_num
        self.fc = fc
        self.ppm = ppm
        self.samp_rate = samp_rate

        ##################################################
        # Variables
        ##################################################
        self.samp_rate_out = samp_rate_out = 1625000.0/6.0*OSR

        ##################################################
        # Blocks
        ##################################################
        self.gsm_receiver_0 = grgsm.receiver(OSR, ([chan_num]), ([]))
        self.gsm_input_0 = grgsm.gsm_input(
            ppm=ppm,
            osr=OSR,
            fc=fc,
            samp_rate_in=samp_rate,
        )
        self.gsm_control_channels_decoder_0 = grgsm.control_channels_decoder()
        self.gsm_clock_offset_control_0 = grgsm.clock_offset_control(fc)
        self.gsm_bcch_ccch_demapper_0 = grgsm.gsm_bcch_ccch_demapper(0)
        #self.gsm_bcch_ccch_demapper_0 = grgsm.universal_ctrl_chans_demapper(0, ([2,6,12,16,22,26,32,36,42,46]), ([1,2,2,2,2,2,2,2,2,2]))

        ##################################################
        # Connections
        ##################################################
        self.msg_connect(self.gsm_bcch_ccch_demapper_0, 'bursts', self, 'bursts')
        self.msg_connect(self.gsm_bcch_ccch_demapper_0, 'bursts', self.gsm_control_channels_decoder_0, 'bursts')
        self.msg_connect(self.gsm_clock_offset_control_0, 'ppm', self.gsm_input_0, 'ppm_in')
        self.msg_connect(self.gsm_control_channels_decoder_0, 'msgs', self, 'msgs')
        self.msg_connect(self.gsm_receiver_0, 'C0', self.gsm_bcch_ccch_demapper_0, 'bursts')
        self.msg_connect(self.gsm_receiver_0, 'measurements', self.gsm_clock_offset_control_0, 'measurements')
        self.connect((self.gsm_input_0, 0), (self.gsm_receiver_0, 0))
        self.connect((self, 0), (self.gsm_input_0, 0))


    def get_OSR(self):
        return self.OSR

    def set_OSR(self, OSR):
        self.OSR = OSR
        self.set_samp_rate_out(1625000.0/6.0*self.OSR)
        self.gsm_input_0.set_osr(self.OSR)

    def get_chan_num(self):
        return self.chan_num

    def set_chan_num(self, chan_num):
        self.chan_num = chan_num

    def get_fc(self):
        return self.fc

    def set_fc(self, fc):
        self.fc = fc
        self.gsm_input_0.set_fc(self.fc)

    def get_ppm(self):
        return self.ppm

    def set_ppm(self, ppm):
        self.ppm = ppm
        self.gsm_input_0.set_ppm(self.ppm)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.gsm_input_0.set_samp_rate_in(self.samp_rate)

    def get_samp_rate_out(self):
        return self.samp_rate_out

    def set_samp_rate_out(self, samp_rate_out):
        self.samp_rate_out = samp_rate_out


class wideband_receiver(grgsm.hier_block):

    def __init__(self, OSR=4, fc=939.4e6, samp_rate=0.4e6):
        grgsm.hier_block.__init__(
            self, "Wideband receiver",
            gr.io_signature(1, 1, gr.sizeof_gr_complex*1),
            gr.io_signature(0, 0, 0),
        )
        self.message_port_register_hier_out("bursts")
        self.message_port_register_hier_out("msgs")
        self.__init(OSR, fc, samp_rate)

    def __init(self, OSR=4, fc=939.4e6, samp_rate=0.4e6):
        ##################################################
        # Parameters
        ##################################################
        self.OSR = OSR
        self.fc = fc
        self.samp_rate = samp_rate
        self.channels_num = int(samp_rate/0.2e6)
        self.OSR_PFB = 2

        ##################################################
        # Blocks
        ##################################################
        self.pfb_channelizer_ccf_0 = pfb.channelizer_ccf(
            self.channels_num,
            (),
            self.OSR_PFB,
            100)
        self.pfb_channelizer_ccf_0.set_channel_map(([]))
        self.create_receivers()

        ##################################################
        # Connections
        ##################################################
        self.connect((self, 0), (self.pfb_channelizer_ccf_0, 0))
        for chan in xrange(0,self.channels_num):
            self.connect((self.pfb_channelizer_ccf_0, chan), (self.receivers_with_decoders[chan], 0))
            self.msg_connect(self.receivers_with_decoders[chan], 'bursts', self, 'bursts')
            self.msg_connect(self.receivers_with_decoders[chan], 'msgs', self, 'msgs')

    def create_receivers(self):
        self.receivers_with_decoders = {}
        for chan in xrange(0,self.channels_num):
            self.receivers_with_decoders[chan] = receiver_with_decoder(fc=self.fc, OSR=self.OSR, chan_num=chan, samp_rate=self.OSR_PFB*0.2e6)

    def get_OSR(self):
        return self.OSR

    def set_OSR(self, OSR):
        self.OSR = OSR
        self.create_receivers()

    def get_fc(self):
        return self.fc

    def set_fc(self, fc):
        self.fc = fc
        self.create_receivers()

    def get_samp_rate(self):
        return self.samp_rate


class wideband_scanner(gr.top_block):

    def __init__(self, rec_len=3, sample_rate=2e6, carrier_frequency=939e6, ppm=0, args=""):

        gr.top_block.__init__(self, "Wideband Scanner")

        self.rec_len = rec_len
        self.sample_rate = sample_rate
        self.carrier_frequency = carrier_frequency
        self.ppm = ppm

        # if no file name is given process data from rtl_sdr source
        print "Args=",args
        self.rtlsdr_source = osmosdr.source( args="numchan=" + str(1) + " " + args )

        self.rtlsdr_source.set_sample_rate(sample_rate)

        # capture half of GSM channel lower than channel center (-0.1MHz)
        # this is needed when even number of channels is captured in order to process full captured bandwidth

        self.rtlsdr_source.set_center_freq(carrier_frequency - 0.1e6, 0)

        # correction of central frequency
        # if the receiver has large frequency offset
        # the value of this variable should be set close to that offset in ppm
        self.rtlsdr_source.set_freq_corr(ppm, 0)

        self.rtlsdr_source.set_dc_offset_mode(2, 0)
        self.rtlsdr_source.set_iq_balance_mode(0, 0)
        self.rtlsdr_source.set_gain_mode(True, 0)
        self.rtlsdr_source.set_bandwidth(sample_rate, 0)

        self.head = blocks.head(gr.sizeof_gr_complex * 1, int(rec_len * sample_rate))

        # shift again by -0.1MHz in order to align channel center in 0Hz
        self.blocks_rotator_cc = blocks.rotator_cc(-2 * pi * 0.1e6 / sample_rate)

        self.wideband_receiver = wideband_receiver(OSR=4, fc=carrier_frequency, samp_rate=sample_rate)
        self.gsm_extract_system_info = grgsm.extract_system_info()


        self.connect((self.rtlsdr_source, 0), (self.head, 0))
        self.connect((self.head, 0), (self.blocks_rotator_cc, 0))
        self.connect((self.blocks_rotator_cc, 0), (self.wideband_receiver,0))
        self.msg_connect(self.wideband_receiver, 'msgs', self.gsm_extract_system_info, 'msgs')

    def set_carrier_frequency(self, carrier_frequency):
        self.carrier_frequency = carrier_frequency
        self.rtlsdr_source.set_center_freq(carrier_frequency - 0.1e6, 0)

def scan(bands=[], sample_rate=2e6, ppm=0, gain=30.0, speed=4):

    found_list = []
    channels_num = int(sample_rate/0.2e6)
    arfcn_list = dict()
    for band in bands:
        print "\nScanning band: %s"% band

        first_arfcn = grgsm.arfcn.get_first_arfcn(band)
        last_arfcn = grgsm.arfcn.get_last_arfcn(band)
        last_center_arfcn = last_arfcn - int((channels_num / 2) - 1)

        current_freq = grgsm.arfcn.arfcn2downlink(first_arfcn + int(channels_num / 2) - 1, band)
        last_freq = grgsm.arfcn.arfcn2downlink(last_center_arfcn, band)
        stop_freq = last_freq + 0.2e6 * channels_num

        while current_freq < stop_freq:

            # silence rtl_sdr output:
            # open 2 fds
            null_fds = [os.open(os.devnull, os.O_RDWR) for x in xrange(2)]
            # save the current file descriptors to a tuple
            save = os.dup(1), os.dup(2)
            # put /dev/null fds on 1 and 2
            os.dup2(null_fds[0], 1)
            os.dup2(null_fds[1], 2)

            # instantiate scanner and processor
            scanner = wideband_scanner(rec_len=6-speed,
                                sample_rate=sample_rate,
                                carrier_frequency=current_freq,
                                ppm=ppm)

            # start recording
            scanner.start()
            scanner.wait()
            scanner.stop()

            # restore file descriptors so we can print the results
            os.dup2(save[0], 1)
            os.dup2(save[1], 2)
            # close the temporary fds
            os.close(null_fds[0])
            os.close(null_fds[1])

            freq_offsets = numpy.fft.ifftshift(numpy.array(range(int(-numpy.floor(channels_num/2)),int(numpy.floor((channels_num+1)/2))))*2e5)
            detected_c0_channels = scanner.gsm_extract_system_info.get_chans()

            if detected_c0_channels:
                chans = numpy.array(scanner.gsm_extract_system_info.get_chans())
                found_freqs = current_freq + freq_offsets[(chans)]

                cell_ids = numpy.array(scanner.gsm_extract_system_info.get_cell_id())
                lacs = numpy.array(scanner.gsm_extract_system_info.get_lac())
                mccs = numpy.array(scanner.gsm_extract_system_info.get_mcc())
                mncs = numpy.array(scanner.gsm_extract_system_info.get_mnc())
                ccch_confs = numpy.array(scanner.gsm_extract_system_info.get_ccch_conf())
                powers = numpy.array(scanner.gsm_extract_system_info.get_pwrs())


                for i in range(0, len(chans)):
                    cell_arfcn_list = scanner.gsm_extract_system_info.get_cell_arfcns(chans[i])
                    neighbour_list = scanner.gsm_extract_system_info.get_neighbours(chans[i])

                    info = ChannelInfo(grgsm.arfcn.downlink2arfcn(found_freqs[i], band), found_freqs[i], cell_ids[i], lacs[i], mccs[i], mncs[i], ccch_confs[i], powers[i], neighbour_list, cell_arfcn_list)

                    if info.arfcn:
                        found_list.append(info)
                        print info.arfcn
                    else:
                        print 'Skipping `None`...'

            scanner = None
            current_freq += channels_num * 0.2e6
    return found_list

if __name__ == '__main__':
    parser = OptionParser(option_class=eng_option, usage="%prog: [options]")
    bands_list = ", ".join(grgsm.arfcn.get_bands())
    parser.add_option("-b", "--band", dest="band", default="900M-Bands",
                      help="Specify the GSM band for the frequency.\nAvailable bands are: " + bands_list)
    parser.add_option("-s", "--samp-rate", dest="samp_rate", type="float", default=2e6,
        help="Set sample rate [default=%default] - allowed values even_number*0.2e6")
    parser.add_option("-p", "--ppm", dest="ppm", type="intx", default=0,
        help="Set frequency correction in ppm [default=%default]")
    parser.add_option("-g", "--gain", dest="gain", type="eng_float", default=24.0,
        help="Set gain [default=%default]")
    parser.add_option("", "--args", dest="args", type="string", default="",
        help="Set device arguments [default=%default]")
    parser.add_option("--speed", dest="speed", type="intx", default=4,
        help="Scan speed [default=%default]. Value range 0-5.")
    parser.add_option("-v", "--verbose", action="store_true",
                      help="If set, verbose information output is printed: ccch configuration, cell ARFCN's, neighbor ARFCN's")
# Detection methods #
    parser.add_option("--no_TIC", action="store_true", default=False, help="Disable the tower information consistency checks.")
    parser.add_option("--no_neighbours", action="store_true", default=False, help="Disable the neighbours consistency checks.")
    parser.add_option("--no_analyzer", action="store_true", default=False, help="Disable the in depth analysis of suspicious BTS.")
#####################
    """
        Dont forget: sudo sysctl kernel.shmmni=32000
    """

    (options, args) = parser.parse_args()

    if options.band is not "900M-Bands":
        if options.band not in grgsm.arfcn.get_bands():
            parser.error("Invalid GSM band\n")

    if options.speed < 0 or options.speed > 5:
        parser.error("Invalid scan speed.\n")

    if (options.samp_rate / 0.2e6) % 2 != 0:
        parser.error("Invalid sample rate. Sample rate must be an even numer * 0.2e6")
    channels_num = int(options.samp_rate/0.2e6)
    if options.band is "900M-Bands":
        to_scan = ['P-GSM',
                   'E-GSM',
                   'R-GSM',
                   #'GSM450',
                   #'GSM480',
                   #'GSM850',  Nothing found
                   #'DCS1800', #BTS found with kal
                   #'PCS1900', #Nothing interesting
                    ]
    else:
        to_scan = [options.band]

    print "GSM bands to be scanned:\n"
    print "\n\t".join(to_scan)

    #scan(bands=to_scan, sample_rate=options.samp_rate, ppm=options.ppm, gain=options.gain, speed=options.speed)
    #exit()

    # Detection methods to be used
    print "\nDetection Methods to be used:"
    if not options.no_TIC:
        print "\tTower Information Consistency Check"
    if not options.no_neighbours:
        print "\tNeighbour Consistency Check"

    arfcn_list = dict()
    for band in to_scan:
        options.band = band
        print "\nScanning band: %s"% band


        first_arfcn = grgsm.arfcn.get_first_arfcn(options.band)
        last_arfcn = grgsm.arfcn.get_last_arfcn(options.band)
        last_center_arfcn = last_arfcn - int((channels_num / 2) - 1)

        current_freq = grgsm.arfcn.arfcn2downlink(first_arfcn + int(channels_num / 2) - 1, options.band)
        last_freq = grgsm.arfcn.arfcn2downlink(last_center_arfcn, options.band)
        stop_freq = last_freq + 0.2e6 * channels_num

        while current_freq < stop_freq:

            # silence rtl_sdr output:
            # open 2 fds
            null_fds = [os.open(os.devnull, os.O_RDWR) for x in xrange(2)]
            # save the current file descriptors to a tuple
            save = os.dup(1), os.dup(2)
            # put /dev/null fds on 1 and 2
            os.dup2(null_fds[0], 1)
            os.dup2(null_fds[1], 2)

            # instantiate scanner and processor
            scanner = wideband_scanner(rec_len=6-options.speed,
                                sample_rate=options.samp_rate,
                                carrier_frequency=current_freq,
                                ppm=options.ppm, args=options.args)

            # start recording
            scanner.start()
            scanner.wait()
            scanner.stop()

            # restore file descriptors so we can print the results
            os.dup2(save[0], 1)
            os.dup2(save[1], 2)
            # close the temporary fds
            os.close(null_fds[0])
            os.close(null_fds[1])

            freq_offsets = numpy.fft.ifftshift(numpy.array(range(int(-numpy.floor(channels_num/2)),int(numpy.floor((channels_num+1)/2))))*2e5)
            detected_c0_channels = scanner.gsm_extract_system_info.get_chans()

            if detected_c0_channels:
                chans = numpy.array(scanner.gsm_extract_system_info.get_chans())
                found_freqs = current_freq + freq_offsets[(chans)]

                cell_ids = numpy.array(scanner.gsm_extract_system_info.get_cell_id())
                lacs = numpy.array(scanner.gsm_extract_system_info.get_lac())
                mccs = numpy.array(scanner.gsm_extract_system_info.get_mcc())
                mncs = numpy.array(scanner.gsm_extract_system_info.get_mnc())
                ccch_confs = numpy.array(scanner.gsm_extract_system_info.get_ccch_conf())
                powers = numpy.array(scanner.gsm_extract_system_info.get_pwrs())

                found_list = dict()
                for i in range(0, len(chans)):
                    cell_arfcn_list = scanner.gsm_extract_system_info.get_cell_arfcns(chans[i])
                    neighbour_list = scanner.gsm_extract_system_info.get_neighbours(chans[i])

                    info = ChannelInfo(grgsm.arfcn.downlink2arfcn(found_freqs[i], options.band), found_freqs[i], cell_ids[i], lacs[i], mccs[i], mncs[i], ccch_confs[i], powers[i], neighbour_list, cell_arfcn_list)

                    found_list[info.arfcn] = info
                    print info.arfcn

            scanner = None
            current_freq += channels_num * 0.2e6
