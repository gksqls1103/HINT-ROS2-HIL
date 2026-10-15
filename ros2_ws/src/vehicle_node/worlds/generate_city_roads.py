#!/usr/bin/env python3
"""Generate an 8 km Gazebo road grid using built-in SDF shapes only."""

from pathlib import Path


WORLD = Path(__file__).with_name("vehicle.sdf")
START = "<!-- GENERATED_CITY_ROADS_START -->"
END = "<!-- GENERATED_CITY_ROADS_END -->"
CENTERS = range(-4000, 4001, 500)
lines = ['<model name="city_road_network"><static>true</static><link name="roads">']


def width(center):
    return 18 if center % 2000 == 0 else 11


def visual(name, x, y, z, length, breadth, height, color):
    lines.append(
        f'<visual name="{name}"><pose>{x:g} {y:g} {z:g} 0 0 0</pose>'
        f'<geometry><box><size>{length:g} {breadth:g} {height:g}</size>'
        f'</box></geometry><material><ambient>{color}</ambient>'
        f'<diffuse>{color}</diffuse></material></visual>'
    )


def solid_box(name, x, y, z, length, breadth, height, color):
    visual(name, x, y, z, length, breadth, height, color)
    lines.append(
        f'<collision name="{name}_collision"><pose>{x:g} {y:g} {z:g} 0 0 0</pose>'
        f'<geometry><box><size>{length:g} {breadth:g} {height:g}</size>'
        f'</box></geometry></collision>'
    )


def cylinder(name, x, y, z, radius, length, color, collidable=False):
    geometry = (f'<geometry><cylinder><radius>{radius:g}</radius>'
                f'<length>{length:g}</length></cylinder></geometry>')
    pose = f'<pose>{x:g} {y:g} {z:g} 0 0 0</pose>'
    lines.append(f'<visual name="{name}">{pose}{geometry}'
                 f'<material><ambient>{color}</ambient><diffuse>{color}</diffuse>'
                 f'</material></visual>')
    if collidable:
        lines.append(f'<collision name="{name}_collision">{pose}{geometry}</collision>')


ASPHALT = "0.15 0.16 0.17 1"
WHITE = "0.9 0.9 0.84 1"
YELLOW = "0.94 0.74 0.22 1"
CONCRETE = "0.48 0.49 0.47 1"
CURB = "0.72 0.72 0.67 1"

# Horizontal roads run through junctions. Vertical roads only fill the gaps,
# so asphalt faces do not overlap and cannot flicker in Gazebo's depth buffer.
for y in CENTERS:
    visual(f"east_west_{y}", 0, y, 0.015, 8000, width(y), 0.03, ASPHALT)

for x in CENTERS:
    for y in range(-4000, 4000, 500):
        lower = y + width(y) / 2
        upper = y + 500 - width(y + 500) / 2
        visual(f"north_south_{x}_{y}", x, (lower + upper) / 2,
               0.015, width(x), upper - lower, 0.03, ASPHALT)

# Paint uses raised, narrow shapes that remain visible against the road.
for y in CENTERS:
    for side in (-1, 1):
        visual(f"ew_edge_{y}_{side}", 0,
               y + side * (width(y) / 2 - 0.3), 0.034,
               8000, 0.11, 0.008, WHITE)
        visual(f"ew_center_{y}_{side}", 0,
               y + side * 0.12, 0.034,
               8000, 0.07, 0.008, YELLOW)

for x in CENTERS:
    for side in (-1, 1):
        visual(f"ns_edge_{x}_{side}",
               x + side * (width(x) / 2 - 0.3), 0,
               0.034, 0.11, 8000, 0.008, WHITE)
        visual(f"ns_center_{x}_{side}",
               x + side * 0.12, 0,
               0.034, 0.07, 8000, 0.008, YELLOW)

# Detailed streetscape around the spawn area. Keep all raised objects beyond
# the 18 m avenue's edge so the vehicle's original test route remains clear.
for side in (-1, 1):
    for start, end in ((-125, -12), (12, 125)):
        center = (start + end) / 2
        length = end - start
        solid_box(f"sidewalk_{side}_{start}", center, side * 10.5, 0.09,
                  length, 2.2, 0.12, CONCRETE)
        visual(f"curb_{side}_{start}", center, side * 9.32, 0.12,
               length, 0.16, 0.18, CURB)

    # Four driving lanes on the avenue; broken white paint divides lanes in
    # each direction. Leave the central intersection unpainted.
    for x in range(-120, 121, 12):
        if abs(x) < 15:
            continue
        visual(f"lane_dash_{side}_{x}", x, side * 4.5, 0.038,
               4, 0.12, 0.006, WHITE)

    for i in range(8):
        y = side * (1.1 + i * 0.9)
        visual(f"crosswalk_{side}_{i}", 14, y, 0.039,
               0.75, 0.5, 0.006, WHITE)

BUILDING_COLORS = (
    "0.57 0.51 0.44 1", "0.42 0.49 0.54 1",
    "0.72 0.68 0.59 1", "0.48 0.43 0.41 1",
)
GLASS = "0.13 0.24 0.31 1"
FRAME = "0.79 0.78 0.7 1"
ROOF = "0.27 0.29 0.31 1"

# Two rows of modest buildings face the road. Each block has a physical shell;
# windows, doors and roof trim are visual only to keep the simulation light.
for side in (-1, 1):
    for index, x in enumerate((-104, -76, -48, -25, 25, 48, 76, 104)):
        depth = 13 if index % 2 else 15
        height = (9, 13, 18, 11)[index % 4]
        y = side * (23 + depth / 2)
        tag = f"building_{side}_{index}"
        solid_box(tag, x, y, height / 2, 17, depth, height,
                  BUILDING_COLORS[index % len(BUILDING_COLORS)])
        visual(f"{tag}_roof", x, y, height + 0.22,
               17.6, depth + 0.6, 0.44, ROOF)
        facade_y = y - side * (depth / 2 + 0.015)
        for floor in range(1, int(height // 3)):
            for column, offset in enumerate((-5.3, -1.8, 1.8, 5.3)):
                visual(f"{tag}_window_{floor}_{column}", x + offset,
                       facade_y, 1.65 + floor * 2.7, 1.65, 0.035, 1.35,
                       GLASS)
                visual(f"{tag}_sill_{floor}_{column}", x + offset,
                       facade_y - side * 0.035, 0.9 + floor * 2.7,
                       1.85, 0.08, 0.12, FRAME)
        visual(f"{tag}_door", x, facade_y - side * 0.025, 1.12,
               1.4, 0.06, 2.22, ROOF)

POLE = "0.40 0.37 0.32 1"
for side in (-1, 1):
    for index, x in enumerate((-116, -60, -16, 16, 60, 116)):
        tag = f"utility_pole_{side}_{index}"
        y = side * 13.2
        cylinder(tag, x, y, 3.9, 0.16, 7.8, POLE, collidable=True)
        visual(f"{tag}_crossarm", x, y, 7.15, 2.2, 0.16, 0.14, POLE)
        for offset in (-0.8, 0, 0.8):
            cylinder(f"{tag}_insulator_{offset}", x + offset, y,
                     7.32, 0.08, 0.21, "0.84 0.83 0.74 1")

lines.append('</link></model>')
world = WORLD.read_text(encoding="utf-8")
assert world.count(START) == 1 and world.count(END) == 1
before, remainder = world.split(START, 1)
_, after = remainder.split(END, 1)
WORLD.write_text(before + START + '\n' + '\n'.join(lines) + '\n' + END + after,
                 encoding="utf-8")
print(f"Generated {WORLD}: 8 km x 8 km, 17 roads per axis, {len(lines) - 2} visuals")
