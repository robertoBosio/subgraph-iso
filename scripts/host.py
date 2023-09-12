import pynq
from pynq import Overlay
from pynq import allocate
from pynq import Clocks
from pprint import pprint
from random import randint as rnd
import numpy as np
import time
import getopt
import argparse
import os.path
import subprocess
import re
from time import perf_counter
from time import sleep

def parse_args():

    parser = argparse.ArgumentParser(description='reads ')
    
    parser.add_argument('path', 
            help='input file using absolute path')
    
    args = parser.parse_args()
  
    if not os.path.isdir(args.path):
        print("Wrong overlay directory path.")
        sys.exit(2)
    
    return args

def subiso(test, path):
  
    HASHTABLES_SPACE = 1 << 28  #~ 67 MB
    BLOOM_SPACE  = 1 << 27  #~ 67 MB
    RESULTS_SPACE = 1 << 29  #~ 134 MB
    MAX_QDATA = 300
    BURST_SIZE = 32
    nfile = 0
    tot_time_bench = 0
    time_limit = 2400
    lab_w = 5
    datagraph_v = 0
    datagraph_e = 0
    querygraph_v = 0
    querygraph_e = 0
    mem_counter = 0
    byte_bloom = 16 * 4
    byte_counter = 4
    byte_edge = 5
   
    ## AXILITE register addresses ##
    # addr_graph = 0x10
    addr_mem0 = 0x10
    addr_mem1 = 0x1c
    addr_mem2 = 0x28
    addr_mem3 = 0x34
    addr_bloom = 0x40
    addr_fifo = 0x4c
    
    addr_qv = 0x58
    addr_qe = 0x60
    addr_de = 0x68
    addr_hash1_w = 0x74
    addr_hash2_w = 0x7c
    addr_dyn_space = 0x84
    
    addr_dyn_fifo = 0x90
    addr_dyn_fifo_ctrl = 0x98
    addr_preproc = 0xa8
    addr_preproc_ctrl = 0xac
    addr_resl = 0x280
    addr_resh = 0x284
    addr_res_ctrl = 0x288

    addr_hit0l = 0x220
    addr_hit0h = 0x224
    addr_hit1l = 0x238
    addr_hit1h = 0x23c
    addr_req0l = 0x250
    addr_req0h = 0x254
    addr_req1l = 0x268
    addr_req1h = 0x26c

    node_t = np.uint32
    label_t = np.uint8
    edge_t = np.dtype([('src', node_t), 
                       ('dst', node_t),
                       ('lsrc', node_t),
                       ('ldst', node_t)]) 

    ol = Overlay(path + "design_1.bit", download=False)
    
    Clocks._instance.PL_CLK_CTRLS[0].DIVISOR0=10
    
    FIFO = allocate(shape=(int(RESULTS_SPACE/np.dtype(edge_t).itemsize),), dtype=edge_t)
    BLOOM = allocate(shape=(BLOOM_SPACE,), dtype=np.uint8)
    MEM = allocate(shape=(int(HASHTABLES_SPACE/np.dtype(node_t).itemsize),), dtype=node_t)
    dynfifo_space = 0

    fres = open(path + "results.txt", "a")

    for data in test.keys():
        datagraph = path + "data/" + data
        counter = 0
        fd = open(datagraph, "r")
        line = fd.readline()
        letter, datagraph_v, datagraph_e = line.split()
        datagraph_v = int(datagraph_v)
        datagraph_e = int(datagraph_e)

        #Computing space for dynamic fifo
        dynfifo_space = datagraph_e + MAX_QDATA;
        dynfifo_space = dynfifo_space - (dynfifo_space % BURST_SIZE) + BURST_SIZE;
        dynfifo_space = int(RESULTS_SPACE / np.dtype(edge_t).itemsize) - dynfifo_space;
        counter = dynfifo_space;

        # Allocating space for map (id -> label)
        datagraph_la = np.empty([datagraph_v], dtype=label_t)

        for v in range(datagraph_v):
            line = fd.readline()
            letter, node, label, degree = line.split()
            datagraph_la[int(node)] = int(label)
    
#        print("Loading", data, "in DDR...", sep=" ", end = "", flush=True)
#        start = perf_counter()
#        for e in range(datagraph_e):
#            line = fd.readline()
#            letter, nodesrc, nodedst = line.split()
#            nodesrc = int(nodesrc)
#            nodedst = int(nodedst)
#            FIFO[counter] = (nodesrc, nodedst, datagraph_la[nodesrc], datagraph_la[nodedst])
#            counter = counter + 1
#        end = perf_counter()
#        print(" Done in ", end - start, "s", sep="", flush=True)


        print(f"Loading {data} in DDR...", end="", flush=True)
        start = time.perf_counter()

        # Adjust the buffer size for optimal performance
        buffer_size = 4096

        while True:
            lines = fd.readlines(buffer_size)
            if not lines:
                break

            for line in lines:
                letter, nodesrc, nodedst = line.split()
                nodesrc, nodedst = int(nodesrc), int(nodedst)
                FIFO[counter] = (nodesrc, nodedst, datagraph_la[nodesrc], datagraph_la[nodedst])
                counter += 1

        end = time.perf_counter()
        print(f" Done in {end - start:.2f} s", flush=True)


        fd.close()
        del datagraph_la
        
        for querytuple in test[data]:
            ol.download()
            Clocks._instance.PL_CLK_CTRLS[0].DIVISOR0=10
            print(Clocks.fclk0_mhz)

            query = querytuple[0]
            
            querygraph = path + "data/" + query
            counter = dynfifo_space + datagraph_e
            fq = open(querygraph, "r")
            line = fq.readline()
            letter, querygraph_v, querygraph_e = line.split()
            querygraph_v = int(querygraph_v)
            querygraph_e = int(querygraph_e)
    
            # Allocating space for map (id -> label)
            querygraph_la = np.empty([querygraph_v], dtype=label_t)
           
            max_degree = 0
            query_vertices = []
            order = []
            adjacency_list = []
            for v in range(querygraph_v):
                line = fq.readline()
                letter, node, label, degree = line.split()
                querygraph_la[int(node)] = int(label)
                query_vertices.append(int(node))
                degree = int(degree)
                adjacency_list.append([])
                if degree > max_degree:
                    max_degree = degree
                    start_node = int(node)

            #Taking as a starting node the one with highest degree 
            order.append(start_node)
            query_vertices.remove(start_node)
            #for x in range(querygraph_v):
            #    FIFO[counter] = (int(x), 0, 0, 0)
            #    counter = counter + 1
            
            tablelist = []
            edge_list = []
            for e in range(querygraph_e):
                line = fq.readline()
                letter, nodesrc, nodedst = line.split()
                labelsrc = querygraph_la[int(nodesrc)]
                labeldst = querygraph_la[int(nodedst)]
                nodesrc = int(nodesrc)
                nodedst = int(nodedst)
                adjacency_list[nodesrc].append(nodedst)
                adjacency_list[nodedst].append(nodesrc)
                edge_list.append((nodesrc, nodedst, labelsrc, labeldst))
                #FIFO[counter] = (nodesrc, nodedst, labelsrc, labeldst)
                #counter = counter + 1
                
                ## Counting number of tables for memory overflow check
                if (nodesrc < nodedst):
                    direction = True

                tupleedge = (labelsrc, labeldst, direction)

                if tablelist.count(tupleedge) == 0:
                    tablelist.append(tupleedge)

            for x in range(querygraph_v - 1):
                max_neigh = 0
                for candidate in query_vertices:
                    neighborhood = 0
                    for neighbor in adjacency_list[candidate]:
                        if neighbor in order:
                            neighborhood += 1

                    if (neighborhood > max_neigh):
                        max_neigh = neighborhood
                        following = candidate
                query_vertices.remove(following)
                order.append(following)

            # Streaming the query order
            for x in range(querygraph_v):
                FIFO[counter] = (order[x], 0, 0, 0)
                counter = counter + 1
            
            for e in range(querygraph_e):
                FIFO[counter] = edge_list[e]
                counter = counter + 1

            fq.close()
            del querygraph_la

            #Resetting memory space
            MEM.fill(0)
            BLOOM.fill(0)
            MEM.flush()
            BLOOM.flush()
            FIFO.flush()
            
            #hash1_w = int(querytuple[2])
            #hash2_w = int(querytuple[3])
            #hash1_w = int(((datagraph_v * 4) / 3900000.0) + 12)
            hash1_w = int(0.4 * np.log(5*(10**7)*datagraph_e)) + 2
            hash2_w = int(min(max_degree + 1, 7))
            #print(order)

            hashtable_spaceused = len(tablelist) * (2**hash1_w) * (2**hash2_w) * byte_counter
            hashtable_spaceused += datagraph_e * byte_edge
            bloom_spaceused = len(tablelist) * (2**hash1_w) * byte_bloom
            blocks = len(tablelist) * 2**(hash1_w + hash2_w - 14)

            while(blocks > 2048):
                hash2_w -= 1
                blocks = len(tablelist) * 2**(hash1_w + hash2_w - 14)
            
            print(f"h1 {hash1_w}, h2 {hash2_w}, blocks: {blocks} max 2048")
            
            # ol.subgraphIsomorphism_0.write(addr_graph, GRAPH_SPACE.device_address)
            ol.subgraphIsomorphism_0.write(addr_mem0, MEM.device_address)
            ol.subgraphIsomorphism_0.write(addr_mem1, MEM.device_address)
            ol.subgraphIsomorphism_0.write(addr_mem2, MEM.device_address)
            ol.subgraphIsomorphism_0.write(addr_mem3, MEM.device_address)
            ol.subgraphIsomorphism_0.write(addr_bloom, BLOOM.device_address)
            ol.subgraphIsomorphism_0.write(addr_fifo, FIFO.device_address)
            ol.subgraphIsomorphism_0.write(addr_hash1_w, hash1_w)
            ol.subgraphIsomorphism_0.write(addr_hash2_w, hash2_w)
            ol.subgraphIsomorphism_0.write(addr_qv, querygraph_v)
            ol.subgraphIsomorphism_0.write(addr_qe, querygraph_e)
            ol.subgraphIsomorphism_0.write(addr_de, datagraph_e)
            ol.subgraphIsomorphism_0.write(addr_dyn_space, dynfifo_space)

            mem_counter = 0;
            mem_counter += FIFO.nbytes
            mem_counter += MEM.nbytes
            mem_counter += BLOOM.nbytes
            
            #Print useful information on memory occupation
            print(data, querytuple, sep=" ", flush=True)
            print(f"Allocated {(mem_counter / (2**20))} Mb. Hash tables" 
                  f" use {((hashtable_spaceused / MEM.nbytes) * 100):.2f}%,"
                  f" bloom use {((bloom_spaceused / BLOOM.nbytes) * 100):.2f}%."
                  f" {dynfifo_space} lines available in fifo.", flush=True)
            
            if (hashtable_spaceused <= MEM.nbytes and bloom_spaceused <= BLOOM.nbytes):
                power = []
                start = perf_counter()

                #Start the kernel
                ol.subgraphIsomorphism_0.write(0x00, 1)
#                while (not(ol.subgraphIsomorphism_0.read(addr_preproc_ctrl))):
#                    pass

#                end_preprocess = perf_counter()
#                print(end_preprocess - start, flush=True)
#                checkpoint = end_preprocess

                while (not (ol.subgraphIsomorphism_0.read(0x00) & 0x2)):
                    with open("/sys/class/hwmon/hwmon2/power1_input") as f_input:
                        power.append(int(f_input.read()))
                    curr_time = perf_counter()
                    if (curr_time - start) > time_limit:
                        print("Failed", flush=True)
                        ol.subgraphIsomorphism_0.write(0x00, 0)
                        break
                    sleep(0.001)
#                while (not (ol.subgraphIsomorphism_0.read(addr_res_ctrl))):
#                    curr_time = perf_counter()
#                    if (curr_time - end_preprocess) > time_limit:
#                        print("Failed", flush=True)
#                        ol.subgraphIsomorphism_0.write(0x00, 0)
#                        break
#                    else:
#                        if (curr_time - checkpoint) > 10:
#                            output = subprocess.run(["xmutil", "platformstats"], 
#                                    stdout=subprocess.PIPE,
#                                    text=True)
#                            res = re.search("([0-9]+) mW", str(output))
#                            print(res.group(1))
#                            print(ol.subgraphIsomorphism_0.read(addr_dyn_fifo), ", ", curr_time - end_preprocess, "s", sep="", flush=True)
#                            checkpoint = curr_time
#                        else :
#                            pass
                end_preprocess = 0
                end_subiso = perf_counter()
#                print(end_preprocess - start, flush=True)
                print(end_subiso - start, flush=True)
                print(f"{np.mean(power)}nW")
                resl = ol.subgraphIsomorphism_0.read(addr_resl)
                resh = ol.subgraphIsomorphism_0.read(addr_resh)
                tot_time = end_subiso - start
                pre_time = end_preprocess - start
                tot_time_bench = tot_time_bench + tot_time

                hit0l = ol.subgraphIsomorphism_0.read(addr_hit0l)
                hit0h = ol.subgraphIsomorphism_0.read(addr_hit0h)
                hit1l = ol.subgraphIsomorphism_0.read(addr_hit1l)
                hit1h = ol.subgraphIsomorphism_0.read(addr_hit1h)
                req0l = ol.subgraphIsomorphism_0.read(addr_req0l)
                req0h = ol.subgraphIsomorphism_0.read(addr_req0h)
                req1l = ol.subgraphIsomorphism_0.read(addr_req1l)
                req1h = ol.subgraphIsomorphism_0.read(addr_req1h)
                print(f"{os.path.basename(querygraph)},"
                      f"{os.path.basename(datagraph)},"
                      f"{hash1_w},{hash2_w}", 
                      f",{(np.mean(power)):.3f}",
                      f",{tot_time:.3f}",
                      f",{(hit0h << 32) | hit0l}",
                      f",{(req0h << 32) | req0l}",
                      f",{(hit1h << 32) | hit1l}",
                      f",{(req1h << 32) | req1l}",
                      f",{(resh << 32) | resl}",
                      sep="",
                      file=fres)
                fres.flush()
                #cycles = int((tot_time - pre_time) * 290000000);
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0xb8);
                #empty1 = ol.subgraphIsomorphism_0.read(0xbc);
                #empty = (empty1 << 32) | empty0;
                #print(f"Propose empty         {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0xd0);
                #empty1 = ol.subgraphIsomorphism_0.read(0xb4);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Edgebuild empty       {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0xe8);
                #empty1 = ol.subgraphIsomorphism_0.read(0xec);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 4
                #print(f"Findmin empty         {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x100);
                #empty1 = ol.subgraphIsomorphism_0.read(0x104);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Readmin counter empty {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x118);
                #empty1 = ol.subgraphIsomorphism_0.read(0x11c);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Readmin edge empty    {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x130);
                #empty1 = ol.subgraphIsomorphism_0.read(0x134);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Homomorphism empty    {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x148);
                #empty1 = ol.subgraphIsomorphism_0.read(0x14c);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Batch build empty     {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x160);
                #empty1 = ol.subgraphIsomorphism_0.read(0x164);
                #empty = (empty1 << 32) | empty0;
                #print(f"Tuplebuild empty      {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x178);
                #empty1 = ol.subgraphIsomorphism_0.read(0x17c);
                #empty = (empty1 << 32) | empty0;
                #print(f"Intersect empty       {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x190);
                #empty1 = ol.subgraphIsomorphism_0.read(0x194);
                #empty = (empty1 << 32) | empty0;
                #empty = empty
                #print(f"Bypass filter empty          {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x1a8);
                #empty1 = ol.subgraphIsomorphism_0.read(0x1ac);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Split empty           {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x1c0);
                #empty1 = ol.subgraphIsomorphism_0.read(0x1c4);
                #empty = (empty1 << 32) | empty0;
                #print(f"Verify empty          {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x1d8);
                #empty1 = ol.subgraphIsomorphism_0.read(0x1dc);
                #empty = (empty1 << 32) | empty0;
                #print(f"Compact empty         {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x1f0);
                #empty1 = ol.subgraphIsomorphism_0.read(0x1f4);
                #empty = (empty1 << 32) | empty0;
                #print(f"Filter empty          {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #empty = 0
                #empty0 = ol.subgraphIsomorphism_0.read(0x208);
                #empty1 = ol.subgraphIsomorphism_0.read(0x20c);
                #empty = (empty1 << 32) | empty0;
                #empty = empty * 2
                #print(f"Assembly empty        {empty} cc, {(empty * 100 / cycles):.2f}%", file=fres)
                #print(f"Cycles: {cycles}", file=fres)
                print(ol.subgraphIsomorphism_0.read(addr_dyn_fifo))
#
#                if c == int(querytuple[1]):
#                    print("OK, solutions: ", c, sep="", flush=True)
#                    print(f"{pre_time:.4f}", 
#                          f"{tot_time:.4f}   OK\n",
#                          sep='\n',
#                          file=fres)
#                else:
#                    print("***** NO *****, expected: ", 
#                          querytuple[1], "\tactual: ", c, sep="",  flush=True)
#                    print(f"{pre_time:.4f}", 
#                          f"{tot_time:.4f} **NO**\n",
#                          sep='\n',
#                          file=fres)
                
            else :
                print("Skipped due to memory overflow.", flush=True)

# nfile += 1
# np.save("/home/ubuntu/" + str(nfile) + ".csv", MEM)
# print("tot time: " + str(np.mean(tot_time_arr)) +
# "+-" + str(np.std(tot_time_arr)) + " s", file=fq)
# print("pre time: " + str(np.mean(pre_time_arr)) +
# "+-" + str(np.std(pre_time_arr)) + " s", file=fq)
# print("power: " + str(np.avg(power_arr)) + "+-" + str(np.std(power_arr)) +
# " (energy: " + str(np.avg(energy_arr)) +
# "+- " + str(np.std(energy_arr)) + ")")
# print(FIFO[4194254:4194354], file=fq)
    
    # print(f"Total test time: {tot_time_bench:.4f}", file=fres)
    fres.close()
    # del FIFO, GRAPH_SPACE, MEM, BLOOM
    del FIFO, MEM, BLOOM

if __name__ == "__main__":
    args = parse_args()
    test = {}
    prev_datagraph = ""
    testfile = open(args.path + "test.txt", "r")

    for line in testfile:
        if not(line.startswith("#")):
            datagraph, querygraph, golden, h1, h2 = line.split()
            datagraph = os.path.basename(datagraph)
            querygraph = os.path.basename(querygraph)
            if (datagraph == prev_datagraph):
                test[datagraph].append((querygraph, golden, h1, h2))
            else:
                test[datagraph] = [(querygraph, golden, h1, h2)]
            prev_datagraph = datagraph
    testfile.close()
    
    subiso(test, args.path)
    
    # Allocating space for streams. #
# SRC_EDG_D = allocate(shape=(datagraph_e,), dtype=node_t)
# DST_EDG_D = allocate(shape=(datagraph_e,), dtype=node_t)
# SRC_EDG_D_L = allocate(shape=(datagraph_e,), dtype=label_t)
# DST_EDG_D_L = allocate(shape=(datagraph_e,), dtype=label_t)
    # Allocating space for streams. #
# SRC_ORD = allocate(shape=(querygraph_v,), dtype=node_t)
# SRC_EDG_Q = allocate(shape=(querygraph_e,), dtype=node_t)
# DST_EDG_Q = allocate(shape=(querygraph_e,), dtype=node_t)
# SRC_EDG_Q_L = allocate(shape=(querygraph_e,), dtype=label_t)
# DST_EDG_Q_L = allocate(shape=(querygraph_e,), dtype=label_t)

        #First transaction query vertex order
# ol.axi_dma_0.sendchannel.transfer(SRC_ORD)
# ol.axi_dma_0.sendchannel.wait()

# Second transaction query edges
# ol.axi_dma_3.sendchannel.transfer(DST_EDG_Q_L)
# ol.axi_dma_2.sendchannel.transfer(SRC_EDG_Q_L)
# ol.axi_dma_1.sendchannel.transfer(DST_EDG_Q)
# ol.axi_dma_0.sendchannel.transfer(SRC_EDG_Q)
# ol.axi_dma_0.sendchannel.wait()

# Third transaction data edges
# ol.axi_dma_3.sendchannel.transfer(DST_EDG_D_L)
# ol.axi_dma_2.sendchannel.transfer(SRC_EDG_D_L)
# ol.axi_dma_1.sendchannel.transfer(DST_EDG_D)
# ol.axi_dma_0.sendchannel.transfer(SRC_EDG_D)
# ol.axi_dma_0.sendchannel.wait()

# Fourth transaction data edges
# ol.axi_dma_3.sendchannel.transfer(DST_EDG_D_L)
# ol.axi_dma_2.sendchannel.transfer(SRC_EDG_D_L)
# ol.axi_dma_1.sendchannel.transfer(DST_EDG_D)
# ol.axi_dma_0.sendchannel.transfer(SRC_EDG_D)
# ol.axi_dma_0.sendchannel.wait()

        #while (not (ol.subgraphIsomorphism_0.read(0x00) & 0x2)):
        #    pass
