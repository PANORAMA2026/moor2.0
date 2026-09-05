"""Source-controlled equipment catalog for the Panorama mooring arrangement.

The entries below are transcribed from drawing 006242A2C010105_01_101832731607(1),
"Mooring and Deck Equipment Arrangement".  Positions are intentionally NOT stored
here: the drawing establishes equipment identity/type, while measured/calibrated
geometry belongs in the persistent mooring geometry database.

This catalog is a source/reference layer, not a substitute for the approved drawing.
"""

DRAWING_ID = "006242A2C010105_01_101832731607(1)"

AFT_EQUIPMENT = [
    # Mooring winches / controls
    {"item": 78, "piece_number": "YA/753C", "type": "WINCH", "description": "Two drums winch and one warping head", "rope_diameter_mm": 72.0},
    {"item": 79, "piece_number": "YA/753D", "type": "WINCH", "description": "Two drums winch and two warping heads", "rope_diameter_mm": 72.0},
    {"item": 80, "piece_number": "YA/753E", "type": "WINCH", "description": "Two drums winch and one warping head", "rope_diameter_mm": 72.0},
    {"item": 81, "piece_number": "YA/753F", "type": "WINCH", "description": "Two drums winch and two warping heads", "rope_diameter_mm": 72.0},
    {"item": 82, "piece_number": "YD/753DB", "type": "REMOTE_CONTROL", "description": "Remote control stand, mooring winch STBD"},
    {"item": 83, "piece_number": "YD/753DA", "type": "REMOTE_CONTROL", "description": "Remote control stand, mooring winch PORT"},

    # Bollards / chocks / fairleads
    {"item": 87, "piece_number": "OF*001BI", "type": "BOLLARD", "description": "Double bollard ND 500", "quantity": 8},
    {"item": 88, "piece_number": "OF*001FS", "type": "BOLLARD_FOUNDATION", "description": "Bollards foundation plate", "quantity": 8},
    {"item": 89, "piece_number": "OF/003PC", "type": "PANAMA_CHOCK", "description": "Panama chock 400x270"},
    {"item": 90, "piece_number": "OF/004PC", "type": "PANAMA_CHOCK", "description": "Panama chock 400x270"},
    {"item": 91, "piece_number": "OF/005PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 92, "piece_number": "OF/006PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 93, "piece_number": "OF/007PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 94, "piece_number": "OF/008PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 95, "piece_number": "OF/009PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 96, "piece_number": "OF/010PC", "type": "FAIRLEAD", "description": "Seven rollers universal fairlead"},
    {"item": 97, "piece_number": "OF/028PC", "type": "FAIRLEAD", "description": "Four rollers universal fairlead"},
    {"item": 98, "piece_number": "OF/029PC", "type": "FAIRLEAD", "description": "Four rollers universal fairlead"},
    {"item": 99, "piece_number": "OF/011PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 100, "piece_number": "OF/012PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 101, "piece_number": "OF/013PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 102, "piece_number": "OF/014PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 103, "piece_number": "OF/025PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 104, "piece_number": "OF/026PC", "type": "FAIRLEAD", "description": "Five rollers universal fairlead"},
    {"item": 105, "piece_number": "OF/015PC", "type": "FAIRLEAD", "description": "Four rollers universal fairlead"},
    {"item": 106, "piece_number": "OF/016PC", "type": "FAIRLEAD", "description": "Four rollers universal fairlead"},

    # Roller leads
    {"item": 110, "piece_number": "OF/021RO", "type": "VERTICAL_GUIDE", "description": "Vertical guide roller ND 350 STBD"},
    {"item": 111, "piece_number": "OF/022RO", "type": "VERTICAL_GUIDE", "description": "Vertical guide roller ND 350 PORT"},
    {"item": 112, "piece_number": "OF*027PC", "type": "EXTERNAL_ROLLER", "description": "External ship roller ND 220", "quantity": 6},
    {"item": 114, "piece_number": "OF/023RO", "type": "DOUBLE_VERTICAL_GUIDE", "description": "Double vertical guide roller ND 350 STBD"},
    {"item": 115, "piece_number": "OF/024RO", "type": "DOUBLE_VERTICAL_GUIDE", "description": "Double vertical guide roller ND 350 STBD"},
    {"item": 116, "piece_number": "OF/025RO", "type": "DOUBLE_VERTICAL_GUIDE", "description": "Double vertical guide roller ND 350 PORT"},
    {"item": 117, "piece_number": "OF/026RO", "type": "DOUBLE_VERTICAL_GUIDE", "description": "Double vertical guide roller ND 350 PORT"},
]

# Items 30-47 and 59-60 are vertical guide rollers.  Their exact final positions
# are intentionally left to the arrangement/lead-line inspection rather than being
# fabricated here.
AFT_VERTICAL_GUIDE_PIECE_NUMBERS = [
    "OF/068PC", "OF/069PC", "OF/070RO", "OF/071RO", "OF/072RO", "OF/073RO",
    "OF/074RO", "OF/075RO", "OF/076RO", "OF/077RO", "OF/079RO", "OF/080RO",
    "OF/081RO", "OF/082RO", "OF/083RO", "OF/084RO", "OF/090RO", "OF/091RO",
    "OF/092RO", "OF/093RO",
]

DRAWING_NOTES = {
    "note_1": "Certain fairleads require lower rope protection (half pipe 168.3 x 10.97 mm).",
    "note_2": "Certain fairleads require upper and lower rope protection; dimensions are specified on the drawing.",
    "note_3": "Mooring fittings are marked with SWL 852 kN.",
    "note_4": "The drawing note states that specified vertical guide rollers and fairleads are to be used with one mooring rope at a time.",
    "note_6": "Final fitting position is to be confirmed after lead-line inspection.",
    "note_7": "Longitudinal position of chain stopper is defined during assembly.",
    "note_12": "Shell fairleads in the forward mooring area have manually operated watertight covers.",
    "note_13": "An opening is provided behind each external roller.",
    "note_14": "Hull structures provide holes/recesses where necessary for roller fairlead removal.",
}


def aft_catalog_by_type(component_type: str):
    """Return source-catalog entries of a given equipment type."""
    return [x for x in AFT_EQUIPMENT if x["type"] == component_type]


def all_known_aft_piece_numbers():
    return [x["piece_number"] for x in AFT_EQUIPMENT] + AFT_VERTICAL_GUIDE_PIECE_NUMBERS
