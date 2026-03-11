from opentrons import protocol_api
import math

metadata = {
    'protocolName': 'Reagent Dispenser to Plate',
    'author': 'Custom Protocol',
    'description': 'Dispense up to 6 reagents with optional pauses, well mixing, and source mixing'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="reagent_layout",
        display_name="Reagent Layout Excel/CSV",
        description="Excel template with reagent configuration"
    )
    
    parameters.add_int(
        variable_name="num_reagents",
        display_name="Number of Reagents",
        description="How many different reagents to use (1-6)",
        default=3,
        minimum=1,
        maximum=6
    )

def run(protocol: protocol_api.ProtocolContext):
    
    # ============================================================================
    # PARAMETERS
    # ============================================================================
    num_reagents = protocol.params.num_reagents
    
    # ============================================================================
    # PARSE EXCEL/CSV DATA
    # ============================================================================
    csv_data = protocol.params.reagent_layout.parse_as_csv()
    csv_rows = list(csv_data)
    
    # Data structures
    reagents = {}  # {reagent_name: {well: volume}}
    reagent_pause = {}  # {reagent_name: True/False}
    reagent_mix_after = {}  # {reagent_name: num_mixes}
    reagent_mix_before = {}  # {reagent_name: {'start': n, 'interval': n, 'times': n}}
    
    current_reagent = None
    current_section = None
    
    for row in csv_rows:
        if len(row) == 0 or not row[0]:
            continue
            
        first_cell = str(row[0]).strip()
        
        # Detect section headers
        if 'Reagent Unique Name:' in first_cell:
            parts = first_cell.split(':')
            if len(parts) > 1:
                current_reagent = parts[1].strip()
                if current_reagent:  # Not empty
                    reagents[current_reagent] = {}
                    current_section = 'volumes'
        
        elif 'Pause Robot Before Starting' in first_cell:
            current_section = 'pause'
            current_reagent = None
            
        elif 'Mix  Each Well After Adding Reagent' in first_cell or 'Mix Each Well After Adding Reagent' in first_cell:
            current_section = 'mix_after'
            current_reagent = None
            
        elif 'Mix the Reagents Before Adding to the Wells' in first_cell:
            current_section = 'mix_before'
            current_reagent = None
        
        # Parse data rows based on current section
        elif current_section == 'volumes' and current_reagent:
            # Volume data rows (A-H)
            if first_cell in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
                row_letter = first_cell
                for col_idx in range(1, min(13, len(row))):
                    try:
                        volume = float(row[col_idx])
                        if volume > 0:
                            well_name = f"{row_letter}{col_idx}"
                            reagents[current_reagent][well_name] = volume
                    except (ValueError, IndexError, TypeError):
                        continue
        
        elif current_section == 'pause':
            # Parse pause settings
            if len(row) > 1:
                reagent_name = str(row[0]).strip()
                pause_value = str(row[1]).strip().upper()
                if reagent_name and pause_value in ['YES', 'NO']:
                    reagent_pause[reagent_name] = (pause_value == 'YES')
        
        elif current_section == 'mix_after':
            # Parse mix after settings
            if len(row) > 1:
                reagent_name = str(row[0]).strip()
                try:
                    num_mixes = int(float(row[1]))
                    if reagent_name and num_mixes >= 0:
                        reagent_mix_after[reagent_name] = num_mixes
                except (ValueError, IndexError, TypeError):
                    continue
        
        elif current_section == 'mix_before':
            # Parse mix before settings
            if len(row) > 3:
                reagent_name = str(row[0]).strip()
                try:
                    mix_start = int(float(row[1]))
                    mix_interval = int(float(row[2]))
                    mix_during = int(float(row[3]))
                    if reagent_name:
                        reagent_mix_before[reagent_name] = {
                            'start': mix_start,
                            'interval': mix_interval,
                            'times': mix_during
                        }
                except (ValueError, IndexError, TypeError):
                    continue
    
    # Keep only the first num_reagents
    reagent_list = list(reagents.keys())[:num_reagents]
    
    # Validate that we have reagents to process
    if not reagent_list:
        protocol.comment("ERROR: No reagents found in CSV file")
        return
    
    protocol.comment("=" * 60)
    protocol.comment("PARSED CONFIGURATION")
    protocol.comment("=" * 60)
    for reagent_name in reagent_list:
        num_wells = len(reagents[reagent_name])
        pause = reagent_pause.get(reagent_name, False)
        mix_after = reagent_mix_after.get(reagent_name, 0)
        mix_before = reagent_mix_before.get(reagent_name, {'start': 0, 'interval': 0, 'times': 0})
        
        protocol.comment(f"\n{reagent_name}:")
        protocol.comment(f"  Wells: {num_wells}")
        protocol.comment(f"  Pause before: {'Yes' if pause else 'No'}")
        protocol.comment(f"  Mix in well: {mix_after} times")
        protocol.comment(f"  Mix at start: {mix_before['start']} times")
        if mix_before['interval'] > 0:
            protocol.comment(f"  Mix every {mix_before['interval']} samples: {mix_before['times']} times")
    protocol.comment("=" * 60)
    
    # ============================================================================
    # LABWARE LOADING
    # ============================================================================
    
    # Load reagent tube rack
    reagent_rack = protocol.load_labware(
        'opentrons_24_aluminumblock_nest_1.5ml_snapcap',
        1,
        'Reagent Tubes'
    )
    
    # Load destination plate
    dest_plate = protocol.load_labware(
        'opentrons_96_wellplate_200ul_pcr_full_skirt',
        2,
        'Destination Plate'
    )
    
    # Load tip racks
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 4)
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 5)
    
    # Load pipette
    p20 = protocol.load_instrument(
        'p20_single_gen2',
        'right',
        tip_racks=[tips_20_1, tips_20_2]
    )
    
    # ============================================================================
    # ASSIGN REAGENTS TO TUBE POSITIONS
    # ============================================================================
    tube_positions = []
    for col in range(1, 7):
        for row in ['A', 'B', 'C', 'D']:
            tube_positions.append(f"{row}{col}")
    
    reagent_tubes = {}
    for idx, reagent_name in enumerate(reagent_list):
        if idx < len(tube_positions):
            reagent_tubes[reagent_name] = reagent_rack[tube_positions[idx]]
            protocol.comment(f"Load {reagent_name} in tube {tube_positions[idx]}")
        else:
            protocol.comment(f"WARNING: Not enough tube positions for {reagent_name}")
    
    protocol.comment("=" * 60)
    protocol.comment("STARTING REAGENT DISPENSING")
    protocol.comment("=" * 60)
    
    # ============================================================================
    # DISPENSE REAGENTS
    # ============================================================================
    
    for reagent_name in reagent_list:
        if reagent_name not in reagents or len(reagents[reagent_name]) == 0:
            protocol.comment(f"Skipping {reagent_name} - no wells defined")
            continue
        
        if reagent_name not in reagent_tubes:
            protocol.comment(f"Skipping {reagent_name} - no tube position assigned")
            continue
        
        # Check if pause is needed
        if reagent_pause.get(reagent_name, False):
            protocol.pause(f"Please add {reagent_name} to tube and click Resume")
        
        protocol.comment(f"\nDispensing {reagent_name}...")
        source_tube = reagent_tubes[reagent_name]
        wells_to_fill = reagents[reagent_name]
        
        # Get mixing parameters
        mix_after = reagent_mix_after.get(reagent_name, 0)
        mix_before = reagent_mix_before.get(reagent_name, {'start': 0, 'interval': 0, 'times': 0})
        
        # Pick up one tip for this reagent
        p20.pick_up_tip()
        
        # Mix at start if specified
        if mix_before['start'] > 0:
            protocol.comment(f"  Mixing {reagent_name} in tube {mix_before['start']} times")
            p20.mix(mix_before['start'], 15, source_tube.bottom(z=1))
            p20.blow_out(source_tube.top(z=-2))
        
        # Dispense to each well
        sample_count = 0
        for well_name, volume in wells_to_fill.items():
            sample_count += 1
            dest_well = dest_plate[well_name]
            
            # Mix during dispensing if interval is reached
            if mix_before['interval'] > 0 and sample_count % mix_before['interval'] == 0 and mix_before['times'] > 0:
                protocol.comment(f"  Mixing {reagent_name} after {sample_count} samples")
                p20.mix(mix_before['times'], 15, source_tube.bottom(z=1))
                p20.blow_out(source_tube.top(z=-2))
            
            # Handle volumes that need splitting (>20µL)
            if volume > 20:
                num_transfers = math.ceil(volume / 20)
                for i in range(num_transfers):
                    transfer_vol = min(20, volume - (i * 20))
                    p20.aspirate(transfer_vol, source_tube.bottom(z=1))
                    p20.dispense(transfer_vol, dest_well.bottom(z=1))
                    if i == num_transfers - 1:  # Last transfer
                        p20.blow_out(dest_well.top(z=-2))
            else:
                p20.aspirate(volume, source_tube.bottom(z=1))
                p20.dispense(volume, dest_well.bottom(z=1))
                p20.blow_out(dest_well.top(z=-2))
            
            # Mix in well if specified
            if mix_after > 0:
                # Calculate mix volume (80% of dispensed volume, max 18µL, min 2µL)
                mix_volume = max(2, min(volume * 0.8, 18))
                p20.mix(mix_after, mix_volume, dest_well.bottom(z=0.5))
                p20.blow_out(dest_well.top(z=-2))
        
        # Drop tip after finishing this reagent
        p20.drop_tip()
        protocol.comment(f"  Completed {len(wells_to_fill)} wells")
    
    # ============================================================================
    # PROTOCOL COMPLETE
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("PROTOCOL COMPLETE!")
    protocol.comment(f"Total reagents dispensed: {len(reagent_list)}")
    protocol.comment("=" * 60)