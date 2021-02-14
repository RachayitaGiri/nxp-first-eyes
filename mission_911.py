import asyncio
from mavsdk import System
from mavsdk.mission import (Mission, MissionItem, MissionPlan)
from geopy.geocoders import Nominatim
from operator import itemgetter

geolocator = Nominatim(user_agent="Vriksh Flight Systems")

def get_drone_type_from_choice(choice):
    switcher = {
        "1": "Medical aid kit",
        "2": "Night vision camera",
        "3": "Speakers"
    }
    drone_type = switcher.get(choice)
    print(f"Drone to be dispatched with \"{drone_type}\".")
    return drone_type

def get_situation_category():
    print("\t1. Medical Emergency\n\
        2. Break-in (nighttime)\n\
        3. Overcrowding\n")
    choice = input("\tDo any of the above categories define the current situation?\n\
        If yes, please enter the number corresponding to the category: ")
    return choice

def get_destination_latitude_longitude():
    try:
        address = input("Enter the address of the destination: ")
        location = geolocator.geocode(address)
        print(location.address)
        lat, lng = location.latitude, location.longitude
        print(lat, lng)
    except:
        lat, lng = None, None
    return lat, lng

async def run():
    drone = System()
    # await drone.connect("serial:///dev/tty.usbmodem01:57600") 
    await drone.connect(system_address="udp://:14540")

    destinations = []
    proceed = "Y"
    while (proceed=="Y" or proceed=="y"):
        situation_type = get_situation_category()
        drone_type = get_drone_type_from_choice(situation_type)
        lat, lng = get_destination_latitude_longitude()
        destinations.append([situation_type, drone_type, [lat, lng]])
        proceed = input("\nDo you need to add more destinations? (Y/N): ")

    # print("\nDispatching the following drones for the corresponding situations:")
    # for dest in destinations:
    #     print(dest)

    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print(f"Drone discovered with UUID: {state.uuid}")
            break

    print_mission_progress_task = asyncio.ensure_future(print_mission_progress(drone))

    running_tasks = [print_mission_progress_task]
    termination_task = asyncio.ensure_future(observe_is_in_air(drone, running_tasks))

    mission_items = []
    print("\nDispatching the following drones for the corresponding situations:")
    for destination in destinations:
        print(destination)
        lat, lng = destination[2][0], destination[2][1]
        mission_items.append(MissionItem(lat,
                                         lng,
                                         25,
                                         10,
                                         True,
                                         float('nan'),
                                         float('nan'),
                                         MissionItem.CameraAction.NONE,
                                         float('nan'),
                                         float('nan')))

    mission_plan = MissionPlan(mission_items)

    await drone.mission.set_return_to_launch_after_mission(True)

    # print("-- Clearing previous missions")
    # await drone.mission.clear_mission()

    print("-- Uploading mission")
    await drone.mission.upload_mission(mission_plan)

    print("-- Arming")
    await drone.action.arm()

    print("-- Starting mission")
    await drone.mission.start_mission()

    await termination_task

async def print_mission_progress(drone):
    async for mission_progress in drone.mission.mission_progress():
        print(f"Mission progress: "
              f"{mission_progress.current}/"
              f"{mission_progress.total}")

async def observe_is_in_air(drone, running_tasks):
    """ Monitors whether the drone is flying or not and
    returns after landing """

    was_in_air = False

    async for is_in_air in drone.telemetry.in_air():
        if is_in_air:
            was_in_air = is_in_air

        if was_in_air and not is_in_air:
            for task in running_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await asyncio.get_event_loop().shutdown_asyncgens()

            return

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())