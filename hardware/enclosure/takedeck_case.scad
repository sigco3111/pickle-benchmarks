// =============================================================================
// TakeDeck TD-01 - USB OBS recording controller
// Parametric enclosure (OpenSCAD 2021.01 or newer)
//
//   openscad -D 'PART="top"' -o top_case.stl takedeck_case.scad
//   PART = "bottom" | "top" | "keycap" | "all"
//
// All dimensions are millimetres and must stay identical to params.json: the
// STL files shipped with this project are generated from params.json by
// generate.py, and generate.py fails if these numbers drift apart.
// Sources for every physical dimension: docs/DIMENSION_SOURCES.md
// =============================================================================

$fn = 64;

// --- case ---------------------------------------------------------------------
CASE_W = 96.0;             // outer width  (X)
CASE_D = 74.0;             // outer depth  (Y)
CASE_H = 24.0;             // outer height (Z)
CASE_WALL = 2.4;
CASE_CORNER_R = 6.0;
CASE_FLOOR = 2.4;
CASE_PLATE = 3.0;          // lid plate thickness
CASE_LID_SKIRT_H = 2.0;    // registration lip that drops into the tray
CASE_LID_SKIRT_WALL = 1.8;
CASE_LID_CLEARANCE = 0.25; // per side, printed fit
CASE_INNER_CORNER_R = 3.6;

// --- keys (Cherry MX, 19.05 mm grid) -------------------------------------------
KEYS_COUNT = 4;
KEYS_PITCH = 19.05;
KEYS_ROW_Y = -19.0;
KEYS_CUTOUT = 14.0;        // plate hole, Cherry datasheet 14 +/- 0.05
KEYS_CLIP_LEDGE = 1.5;     // thickness the switch clips latch under
KEYS_RECESS = 16.2;        // relief pocket so the 15.6 mm housing clears
KEYS_BODY_BELOW_PLATE = 13.6;
KEYS_PIN_LEN = 3.3;

// --- OLED (0.96" SSD1306 I2C module, 27.3 x 27.3 x 2.37) -----------------------
OLED_MODULE_W = 27.3;
OLED_MODULE_D = 27.3;
OLED_MODULE_H = 2.37;
OLED_CENTER_X = 0.0;
OLED_CENTER_Y = 16.0;
OLED_WINDOW_W = 24.4;
OLED_WINDOW_H = 13.6;
OLED_RING_OUTER = 30.9;
OLED_RING_CORNER_R = 2.0;
OLED_MODULE_CLEARANCE = 0.4;
OLED_LEDGE_W = 1.8;
OLED_LEDGE_H = 1.2;
OLED_RING_BOTTOM_Z = 17.4;

// --- recording LED (5 mm red, 5.9 mm flange) -----------------------------------
LED_DIAMETER = 5.0;
LED_FLANGE = 5.9;
LED_HOLE = 5.05;
LED_LIP_HOLE = 4.4;
LED_LIP_H = 0.4;
LED_COUNTERBORE = 6.2;
LED_COUNTERBORE_H = 0.6;
LED_CENTER_X = 0.0;
LED_CENTER_Y = -4.5;

// --- screws (M2.5 x 8 self tapping into printed bosses) ------------------------
SCREWS_PILOT_D = 2.05;
SCREWS_CLEAR_D = 2.8;
SCREWS_CB_D = 5.0;
SCREWS_CB_H = 1.2;
SCREWS_BOSS_D = 6.0;
SCREWS_BOSS_TOP_Z = 19.0;

// --- XIAO RP2040 board (21 x 17.8 x 1.6, USB-C on the rear short edge) ---------
XIAO_BOARD_W = 21.0;
XIAO_BOARD_D = 17.8;
XIAO_BOARD_T = 1.6;
XIAO_BOARD_Z = 3.4;
XIAO_Y_FRONT = 16.2;
XIAO_Y_BACK = 34.0;
XIAO_POCKET_D = 1.0;
XIAO_RAIL_H = 2.0;
XIAO_RAIL_W = 1.3;
XIAO_RAIL_GAP = 0.1;
XIAO_USB_CUT_W = 9.6;
XIAO_USB_CUT_H = 3.6;
XIAO_USB_CUT_Z = 4.9;
XIAO_USB_PLUG_W = 8.34;
XIAO_USB_PLUG_H = 2.56;
XIAO_USB_BODY_H = 3.26;

// --- keycap (1u, MX cross socket) ----------------------------------------------
KEYCAP_SIZE = 18.0;
KEYCAP_CORNER_R = 1.5;
KEYCAP_HEIGHT = 8.0;
KEYCAP_RIM_Z = 28.6;       // bottom rim above the plate, clears on 4 mm travel
KEYCAP_SKIRT_RECESS = 16.0;
KEYCAP_SKIRT_H = 2.0;
KEYCAP_STEM_CROSS_A = 4.2;
KEYCAP_STEM_CROSS_B = 1.35;
KEYCAP_STEM_DEPTH = 5.5;
KEYCAP_TOP_WALL = 2.5;

// --- feet ----------------------------------------------------------------------
FEATURES_FEET_D = 8.0;
FEATURES_FEET_DEPTH = 0.8;
FEATURES_FEET_INSET = 8.0;

// Key and screw positions (same values as params.json)
KEY_X = [-28.575, -9.525, 9.525, 28.575];
SCREW_XY = [[-41.0, -30.0], [41.0, -30.0], [-41.0, 30.0], [41.0, 30.0]];

PART = "all";

PLATE_Z0 = CASE_H - CASE_PLATE;   // 21.0

module rounded_rect(w, d, r) {
    hull()
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (w / 2 - r), sy * (d / 2 - r)])
                circle(r = r);
}

module bottom_case() {
    difference() {
        union() {
            difference() {
                // tray: floor + walls
                linear_extrude(height = PLATE_Z0)
                    rounded_rect(CASE_W, CASE_D, CASE_CORNER_R);
                translate([0, 0, CASE_FLOOR])
                    linear_extrude(height = PLATE_Z0 - CASE_FLOOR + 1)
                        rounded_rect(CASE_W - 2 * CASE_WALL, CASE_D - 2 * CASE_WALL,
                                     CASE_INNER_CORNER_R);
            }
            // screw bosses
            for (p = SCREW_XY)
                translate([p[0], p[1], CASE_FLOOR])
                    cylinder(d = SCREWS_BOSS_D, h = SCREWS_BOSS_TOP_Z - CASE_FLOOR);
            // XIAO rails and front stop
            for (sx = [-1, 1])
                translate([sx * (XIAO_BOARD_W / 2 + XIAO_RAIL_GAP + XIAO_RAIL_W / 2),
                           (XIAO_Y_FRONT + XIAO_Y_BACK) / 2, CASE_FLOOR])
                    cube([XIAO_RAIL_W, XIAO_Y_BACK - XIAO_Y_FRONT, XIAO_RAIL_H], center = false);
            translate([-XIAO_BOARD_W / 2, XIAO_Y_FRONT - 0.8, CASE_FLOOR + XIAO_POCKET_D / 2])
                cube([XIAO_BOARD_W, 0.8, XIAO_POCKET_D], center = false);
        }
        // USB-C opening in the rear wall
        translate([-XIAO_USB_CUT_W / 2, CASE_D / 2 - 4, XIAO_USB_CUT_Z])
            cube([XIAO_USB_CUT_W, 6, XIAO_USB_CUT_H]);
        // screws: pilot holes
        for (p = SCREW_XY)
            translate([p[0], p[1], CASE_FLOOR - 0.5])
                cylinder(d = SCREWS_PILOT_D, h = SCREWS_BOSS_TOP_Z - CASE_FLOOR + 1);
        // board pocket
        translate([-(XIAO_BOARD_W + 0.4) / 2, XIAO_Y_FRONT - 0.2, CASE_FLOOR])
            cube([XIAO_BOARD_W + 0.4, XIAO_Y_BACK - XIAO_Y_FRONT + 0.4, XIAO_POCKET_D]);
        // feet recesses
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (CASE_W / 2 - FEATURES_FEET_INSET),
                       sy * (CASE_D / 2 - FEATURES_FEET_INSET), -0.5])
                cylinder(d = FEATURES_FEET_D, h = FEATURES_FEET_DEPTH + 0.5);
    }
}

module top_case() {
    difference() {
        union() {
            // plate
            linear_extrude(height = CASE_H)
                rounded_rect(CASE_W, CASE_D, CASE_CORNER_R);
            // registration skirt
            translate([0, 0, PLATE_Z0 - CASE_LID_SKIRT_H])
                linear_extrude(height = CASE_LID_SKIRT_H)
                    difference() {
                        rounded_rect(CASE_W - 2 * CASE_WALL - 2 * CASE_LID_CLEARANCE,
                                     CASE_D - 2 * CASE_WALL - 2 * CASE_LID_CLEARANCE,
                                     CASE_INNER_CORNER_R);
                        rounded_rect(CASE_W - 2 * CASE_WALL - 2 * CASE_LID_CLEARANCE - 2 * CASE_LID_SKIRT_WALL,
                                     CASE_D - 2 * CASE_WALL - 2 * CASE_LID_CLEARANCE - 2 * CASE_LID_SKIRT_WALL,
                                     CASE_INNER_CORNER_R - CASE_LID_SKIRT_WALL);
                    }
            // OLED retaining ring + ledge
            translate([OLED_CENTER_X, OLED_CENTER_Y, OLED_RING_BOTTOM_Z])
                linear_extrude(height = PLATE_Z0 - OLED_RING_BOTTOM_Z)
                    difference() {
                        rounded_rect(OLED_RING_OUTER, OLED_RING_OUTER, OLED_RING_CORNER_R);
                        rounded_rect(OLED_MODULE_W + 2 * OLED_MODULE_CLEARANCE,
                                     OLED_MODULE_D + 2 * OLED_MODULE_CLEARANCE, 0.6);
                    }
            translate([OLED_CENTER_X, OLED_CENTER_Y, OLED_RING_BOTTOM_Z])
                linear_extrude(height = OLED_LEDGE_H)
                    difference() {
                        rounded_rect(OLED_RING_OUTER, OLED_RING_OUTER, OLED_RING_CORNER_R);
                        rounded_rect(OLED_MODULE_W + 2 * OLED_MODULE_CLEARANCE - 2 * OLED_LEDGE_W,
                                     OLED_MODULE_D + 2 * OLED_MODULE_CLEARANCE - 2 * OLED_LEDGE_W, 1.0);
                    }
            // LED retaining lip
            translate([LED_CENTER_X, LED_CENTER_Y, CASE_H - LED_LIP_H])
                difference() {
                    cylinder(d = LED_HOLE + 0.01, h = LED_LIP_H);
                    cylinder(d = LED_LIP_HOLE, h = LED_LIP_H + 0.2);
                }
        }
        // switch holes and clip relief
        for (x = KEY_X) {
            translate([x - KEYS_CUTOUT / 2, KEYS_ROW_Y - KEYS_CUTOUT / 2, PLATE_Z0 - 1])
                cube([KEYS_CUTOUT, KEYS_CUTOUT, CASE_PLATE + 2]);
            translate([x - KEYS_RECESS / 2, KEYS_ROW_Y - KEYS_RECESS / 2, PLATE_Z0])
                cube([KEYS_RECESS, KEYS_RECESS, CASE_PLATE - KEYS_CLIP_LEDGE]);
        }
        // OLED window
        translate([OLED_CENTER_X - OLED_WINDOW_W / 2, OLED_CENTER_Y - OLED_WINDOW_H / 2, PLATE_Z0 - 1])
            cube([OLED_WINDOW_W, OLED_WINDOW_H, CASE_PLATE + 2]);
        // LED bore
        translate([LED_CENTER_X, LED_CENTER_Y, PLATE_Z0 - 0.1])
            cylinder(d = LED_COUNTERBORE, h = LED_COUNTERBORE_H + 0.1);
        translate([LED_CENTER_X, LED_CENTER_Y, PLATE_Z0 - 1])
            cylinder(d = LED_HOLE, h = CASE_PLATE + 2);
        // screws: clearance + counterbore
        for (p = SCREW_XY) {
            translate([p[0], p[1], PLATE_Z0 - 1]) cylinder(d = SCREWS_CLEAR_D, h = CASE_PLATE + 2);
            translate([p[0], p[1], CASE_H - SCREWS_CB_H]) cylinder(d = SCREWS_CB_D, h = SCREWS_CB_H + 1);
        }
    }
}

module keycap() {
    difference() {
        translate([0, 0, KEYCAP_RIM_Z])
            linear_extrude(height = KEYCAP_HEIGHT)
                rounded_rect(KEYCAP_SIZE, KEYCAP_SIZE, KEYCAP_CORNER_R);
        translate([-KEYCAP_SKIRT_RECESS / 2, -KEYCAP_SKIRT_RECESS / 2, KEYCAP_RIM_Z - 0.1])
            cube([KEYCAP_SKIRT_RECESS, KEYCAP_SKIRT_RECESS, KEYCAP_SKIRT_H + 0.1]);
        translate([0, 0, KEYCAP_RIM_Z])
            linear_extrude(height = KEYCAP_STEM_DEPTH)
                union() {
                    square([KEYCAP_STEM_CROSS_A, KEYCAP_STEM_CROSS_B], center = true);
                    square([KEYCAP_STEM_CROSS_B, KEYCAP_STEM_CROSS_A], center = true);
                }
    }
}

if (PART == "bottom") bottom_case();
else if (PART == "top") top_case();
else if (PART == "keycap") keycap();
else {
    bottom_case();
    translate([0, 0, 0]) top_case();
}
