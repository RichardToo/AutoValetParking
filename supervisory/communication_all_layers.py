import curses
from ipdb import set_trace as st
import numpy as np
import trio
import random

average_arrival_rate = 1 # per second
beta = 1/average_arrival_rate
average_park_time = 1 # seconds
max_buffer_size = np.inf


def get_current_time():
    return trio.current_time() - start_time

def create_unidirectional_channel(sender, receiver, max_buffer_size):
    out_channel, in_channel = trio.open_memory_channel(max_buffer_size)
    sender.out_channels[receiver.name] = out_channel
    receiver.in_channels[sender.name] = in_channel

def create_bidirectional_channel(compA, compB, max_buffer_size):
    create_unidirectional_channel(sender=compA, receiver=compB, max_buffer_size=max_buffer_size)
    create_unidirectional_channel(sender=compB, receiver=compA, max_buffer_size=max_buffer_size)

class CarInfo:
    def __init__(self, arrive_time, depart_time):
        self.arrive_time = arrive_time
        self.depart_time = depart_time

class BoxComponent:
    def __init__(self):
        self.in_channels = dict()
        self.out_channels = dict()

    def _initialize_channels(self, num_channels):
        channels = []
        for _ in range(num_channels):
            channels.append(None)
        return channels

    def _find_open_channel(self, channel_list):
        for idx in range(len(channel_list)):
            if channel_list[idx] == None:
                return idx
        # all channels are closed!
        return -1

class Planner(BoxComponent):
    def __init__(self,nursery):
        super().__init__()
        self.name = self.__class__.__name__
        self.ref = None
        self.nursery = nursery

    async def send_directive_to_car(self, car, ref):
        print('Sending Directive to {0}'.format(car.name))
        await self.out_channels[car.name].send(ref)

    async def run(self):
        ref = [[0,0],[1,1]]
        async for car in self.in_channels['Scheduler']:
            create_bidirectional_channel(self, car, max_buffer_size=np.inf)
            self.nursery.start_soon(car.run)
            await self.send_directive_to_car(car, ref)


class Car(BoxComponent):
    def __init__(self, arrive_time, depart_time):
        super().__init__()
        self.name = 'Car {}'.format(id(self))
        self.arrive_time = arrive_time
        self.depart_time = depart_time
        self.ref = None

    async def update_planner_command(self):
        print('{0} - Receiving Directive from Planner'.format(self.name))
        self.ref = await self.in_channels['Planner'].receive()

    async def track_reference(self):
        #self.ref = await self.in_channels['Planner'].receive()
        print('Tracking reference...' + str(self.ref))
        await trio.sleep(1)

    async def times_up(self):
        now = get_current_time()
        if self.depart_time >= now:
            print('{} is requested'.format(self.name))
            #await self.out_channels['Planner'].send()

    async def run(self):
        async with trio.open_nursery() as nursery:
            await self.update_planner_command()
            await self.track_reference()
            await self.times_up()

class Scheduler(BoxComponent):
    def __init__(self):
        super().__init__()
        self.name = self.__class__.__name__
        self.cars = []
        #self.nursery = nursery

    async def send_directive_to_planner(self, car):
        await self.out_channels['Planner'].send(car)

    #async def send_command_to_car(self, car, ref):
        #await self.out_channels[car.name].send(ref)

    async def process_queue(self):
        ref = [[0,0],[1,1]]
        accept_condition = True
        async for car in self.in_channels['OutsideWorld']:
            if accept_condition:
                print('{} has been accepted!'.format(car.name))
                #create_bidirectional_channel(self, planner, max_buffer_size=np.inf)
                #create_bidirectional_channel(planner, car, max_buffer_size=np.inf)
                #self.nursery.start_soon(car.run)
                await self.send_directive_to_planner(car)
            else:
                print('a car has been rejected!')

    async def run(self):
        await self.process_queue()

class OutsideWorld(BoxComponent):
    def __init__(self, average_arrival_rate, average_park_time):
        super().__init__()
        self.name = self.__class__.__name__
        self.average_arrival_rate = average_arrival_rate
        self.average_park_time = average_park_time

    def generate_car(self):
        arrive_time = get_current_time()
        depart_time = arrive_time + np.random.exponential(self.average_park_time)
        car = Car(arrive_time=arrive_time, depart_time=depart_time)
        return car

    async def run(self):
        while True:
            # spawns cars according to exponential distribution
            await trio.sleep(np.random.exponential(1/self.average_arrival_rate))
            car = self.generate_car()
            print("Car with ID {0} arrives at {1:.3f}".format(car.name, car.arrive_time))
            await self.out_channels['Scheduler'].send(car)
            # Random sleeps help trigger the problem more reliably
            await trio.sleep(random.random())

async def main():
    global start_time
    start_time = trio.current_time()
    all_components = []
    async with trio.open_nursery() as nursery:
        scheduler = Scheduler()#(nursery=nursery)
        planner = Planner(nursery=nursery)
        all_components.append(scheduler)
        all_components.append(planner)
        outside_world = OutsideWorld(average_arrival_rate = average_arrival_rate, average_park_time = average_park_time)
        all_components.append(outside_world)

        create_bidirectional_channel(scheduler,planner,max_buffer_size=np.inf)
        create_unidirectional_channel(sender=outside_world, receiver=scheduler, max_buffer_size=np.inf)

        for comp in all_components:
            nursery.start_soon(comp.run)

trio.run(main)
