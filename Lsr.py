# Python Version: 3.7

import socket
import sys
import time
import datetime
import threading



class Router:
    def __init__(self):
        self.neighbours_lock = threading.Lock()
        self.ROUTE_UPDATE_INTERVAL = 30
        self.router_id = "router_id_init"
        self.port_id = "port_id_init"
        self.router_neighbour_number = "router_neighbour_number_init"
        self.split_symbol = " "
        self.neighbours = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ### shared data, need lock
        self.retransmit_dic = {}
        self.retransmit_dic_lock = threading.Lock()

        self.neighbours_status = {}
        self.neighbours_status_lock = threading.Lock()

        self.neighbours_status_changed = {}
        self.neighbours_status_changed_lock = threading.Lock()

        self.router_map_dict = {}
        self.router_map_dict_lock = threading.Lock()

        self.heartbeat_dic = {}
        self.heartbeat_dic_lock = threading.Lock()

    def _send_msg(self):
        while True:
            router_map_list = []
            for i in range(len(self.neighbours)):
                cost = self.neighbours[i][1]

                self.neighbours_status_lock.acquire()
                if self.neighbours_status[self.neighbours[i][0]] == 0:
                    cost = "-1"
                self.neighbours_status_lock.release()

                router_map_list.append(self.router_id)
                router_map_list.append(self.neighbours[i][0])
                router_map_list.append(cost)

                self.router_map_dict_lock.acquire()
                self.router_map_dict[
                    (self.router_id, self.neighbours[i][0])
                ] = cost
                self.router_map_dict_lock.release()

            router_map_str = self.split_symbol.join(router_map_list)

            for i in range(int(self.router_neighbour_number)):
                msg_list = [
                    "FROM",
                    self.router_id,
                    "TO",
                    self.neighbours[i][0],
                    self.router_id,
                    self.neighbours[i][0],
                    router_map_str,
                ]
                msg = self.split_symbol.join(msg_list)
                msg_sent = msg + self.split_symbol + str(len(msg))
                self.sock.sendto(
                    msg_sent.encode("utf-8"),
                    ("127.0.0.1", int(self.neighbours[i][-1])),
                )
            time.sleep(1)

    def _receive_msg(self):
        while True:
            ### decode recieved message ###
            data = self.sock.recv(10240)
            data_list = data.decode("utf-8").split(self.split_symbol)
            data_str = self.split_symbol.join(data_list[0:-1])

            ### check packet mesage integrity ###
            if data_list[-1] != str(len(data_str)):
                print("error recv data: " + str(data_list) + "|" + data_str)
                continue

            ### handle heartbeat message ###
            if data_list[0] == "heartbeat":
                # self.heartbeat_dic_lock.acquire()
                self.heartbeat_dic[data_list[2]] = (data_str, time.time())
                # self.heartbeat_dic_lock.release()
                continue

            ### saving recieved router map information ###
            i = 6  #  start at 6th_pos, passing the begining FROM X TO Y 1 2
            while i < len(data_list) - 1:
                self.router_map_dict[
                    (data_list[i], data_list[i + 1])
                ] = data_list[i + 2]
                i += 3

            ### retransmit recieved message ###
            self._retransmit(data_list)

    def _heartbeat(self):  # send heartbeat packet to neighbour every 0.3s
        while True:
            for i in range(int(self.router_neighbour_number)):
                msg_list = [
                    "heartbeat",
                    "FROM",
                    self.router_id,
                    "TO",
                    self.neighbours[i][0],
                ]
                msg = self.split_symbol.join(msg_list)
                msg_sent = msg + self.split_symbol + str(len(msg))
                self.sock.sendto(
                    msg_sent.encode("utf-8"),
                    ("127.0.0.1", int(self.neighbours[i][-1])),
                )
            time.sleep(0.3)

    def _check_neigbor(self):
        while True:

            for i in range(int(self.router_neighbour_number)):
                changed = False
                self.neighbours_status_lock.acquire()
                if self.neighbours[i][0] not in self.heartbeat_dic:
                    self.neighbours_status[self.neighbours[i][0]] = 0
                elif (
                    time.time() - self.heartbeat_dic[self.neighbours[i][0]][1]
                    > 0.4
                ):  # to long not recv packet
                    if self.neighbours_status[self.neighbours[i][0]] == 1:
                        changed = True
                        self.neighbours_status_changed_lock.acquire()
                        self.neighbours_status_changed[
                            self.neighbours[i][0]
                        ] = 1
                        self.neighbours_status_changed_lock.release()

                    self.neighbours_status[
                        self.neighbours[i][0]
                    ] = 0  # router : neighbours[i][0] is down
                    # self.neighbours_status_lock.release()
                else:
                    if self.neighbours_status[self.neighbours[i][0]] == 0:
                        changed = True
                        self.neighbours_status_changed_lock.acquire()
                        self.neighbours_status_changed[
                            self.neighbours[i][0]
                        ] = 1
                        self.neighbours_status_changed_lock.release()

                    self.neighbours_status[self.neighbours[i][0]] = 1
                    # self.neighbours_status_lock.release()
                if changed:
                    # print("router status changed!")
                    # print(self.neighbours_status)
                    pass
                self.neighbours_status_lock.release()
            time.sleep(0.4)  # check neighbours status every 0.4 sec

    def _retransmit(self, data_list):
        msg_meta = self.split_symbol.join(data_list[4:-1])
        for i in range(len(self.neighbours)):
            tag = (
                self.router_id,
                self.neighbours[i][0],
                data_list[4],
                data_list[5],
            )
            self.retransmit_dic_lock.acquire()
            self.neighbours_status_changed_lock.acquire()
            if self.neighbours[i][0] == data_list[1]:
                self.neighbours_status_changed_lock.release()
                self.retransmit_dic_lock.release()
                continue
            elif tag not in self.retransmit_dic:
                self.retransmit_dic[tag] = (msg_meta, time.time())
                self.neighbours_status_changed_lock.release()
                self.retransmit_dic_lock.release()
            elif (
                self.retransmit_dic[tag][0] == msg_meta
                # and time.time() - self.retransmit_dic[tag][1] < 1
                and self.neighbours_status_changed[self.neighbours[i][0]] == 0
            ):
                self.neighbours_status_changed_lock.release()
                self.retransmit_dic_lock.release()
                continue
            else:
                self.retransmit_dic[tag] = (msg_meta, time.time())
                self.neighbours_status_changed[self.neighbours[i][0]] = 0
                self.neighbours_status_changed_lock.release()
                self.retransmit_dic_lock.release()
            msg = (
                "FROM"
                + self.split_symbol
                + self.router_id
                + self.split_symbol
                + "TO"
                + self.split_symbol
                + self.neighbours[i][0]
                + self.split_symbol
                + msg_meta
            )
            msg_sent = msg + self.split_symbol + str(len(msg))
            self.sock.sendto(
                msg_sent.encode("utf-8"),
                ("127.0.0.1", int(self.neighbours[i][-1])),
            )

    def _dijkstra_path(self):
        def get_path(dest):
            path=dest
            a = prev[dest]
            while True:
                if a == self.router_id:
                    path=self.router_id+path
                    break
                path=a+path
                a=prev[a]

            return path
        while 1:
            # print("Path caculating")

            # self.neighbours_status_lock.acquire()
            # neighbours_status = self.neighbours_status.copy()
            # self.neighbours_status_lock.release()
            # print(neighbours_status)

            self.router_map_dict_lock.acquire()
            router_map_dict = self.router_map_dict.copy()
            self.router_map_dict_lock.release()
            # print(router_map_dict)
            # for (a, b) in sorted(router_map_dict.keys()):
            #     print(
            #         "From %s to %s Cost %s " % (a, b, router_map_dict[(a, b)])
            #     )

            N = set()
            N.add(self.router_id)  # add start router id to N

            all_routers = set()
            for (a, b) in router_map_dict.keys():
                all_routers.add(a)
                all_routers.add(b)
            # print(sorted(all_routers))

            router_neighbours_dic = {}
            for item in all_routers:
                neighbours_list = []
                for (a, b) in router_map_dict.keys():
                    if a == item:
                        neighbours_list.append(b)
                router_neighbours_dic[item] = neighbours_list
            # print(router_neighbours_dic)

            dist = {}
            prev = {}
            ### init
            N.add(self.router_id)
            for i in all_routers:
                if i == self.router_id:
                    continue
                elif (
                    i in router_neighbours_dic[self.router_id]
                    and router_map_dict[(self.router_id, i)] != "-1"
                ):
                    # all distance from self.router_id to i
                    dist[i] = float(router_map_dict[(self.router_id, i)])
                    prev[i] = self.router_id
                else:
                    dist[i] = float(-1)
                    # prev[i] =
            #print(self.router_id, dist, prev)
            #print("after")
            while len(N) < len(all_routers):
                valid_dist = []
                for id in all_routers:
                    if id in N:
                        continue
                    elif dist[id] >= 0:
                        valid_dist.append((dist[id], id))
                if valid_dist == []:
                    for id in dist.keys():
                        if id not in N:
                            w = id
                            # min_dist = float(-1)
                            N.add(w)
                            break
                else:
                    #print(valid_dist)
                    (_, w) = sorted(valid_dist)[0]
                    N.add(w)
                for v in router_neighbours_dic[w]:
                    if dist[w] == float(-1):
                        break
                    if v in N:
                        continue
                    if router_map_dict[(w, v)] == '-1':
                        continue
                    if (
                        dist[v] == float(-1)
                        or dist[w] + float(router_map_dict[(w, v)]) < dist[v]
                    ):
                        dist[v] = dist[w] + float(router_map_dict[(w, v)])
                        prev[v] = w
            # print(self.router_id, dist, prev)
            print("I am Router %s" % self.router_id)
            for dest in sorted(dist.keys()):
                if dist[dest] == float(-1):
                    continue
                path = get_path(dest)
                cost = dist[dest]
                if cost != float(-1):
                    print("Least cost path to router %s:%s and the cost is %.1f" % (dest, path, cost))
            time.sleep(self.ROUTE_UPDATE_INTERVAL)
            

    def run(self, router_config):
        try:
            with open(router_config, "r") as f:
                contents = f.read()
            split_content = contents.split()
            self.router_id = split_content[0]
            self.port_id = split_content[1]
            self.router_neighbour_number = split_content[2]
            i = 3
            while i < len(split_content):
                self.neighbours.append([])
                for j in range(0, 3):
                    self.neighbours[-1].append(split_content[i + j])
                i += 3
        except ValueError:
            print("Invalid input.")

        ### initialize self.neighbours_status
        # self.neighbours_status_lock.acquire()
        for i in range(len(self.neighbours)):
            self.neighbours_status[self.neighbours[i][0]] = 0
        # self.neighbours_status_lock.release()

        ### initialize self.neighbours_status_changed
        # self.neighbours_status_changed_lock.acquire()
        for i in range(len(self.neighbours)):
            self.neighbours_status_changed[self.neighbours[i][0]] = 0
        # self.neighbours_status_changed_lock.release()

        self.sock.bind(("127.0.0.1", int(self.port_id)))
        # print("neighbours: " + str(self.neighbours))
        t1 = threading.Thread(target=self._send_msg)
        t2 = threading.Thread(target=self._receive_msg)
        t3 = threading.Thread(target=self._check_neigbor)
        t4 = threading.Thread(target=self._dijkstra_path)
        t5 = threading.Thread(target=self._heartbeat)

        t1.start()
        t2.start()
        t3.start()
        t4.start()
        t5.start()

        t1.join()
        t2.join()
        t3.join()
        t4.join()
        t5.join()
        print("this should not print out")


if __name__ == "__main__":
    r = Router()
    r.run(sys.argv[1])
