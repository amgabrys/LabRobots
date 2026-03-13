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
    # PARSE EXCEL/CSV DATA - MODIFIED FOR HORIZONTAL LAYOUT
    # ============================================================================
    csv_data = protocol.params.reagent_layout.parse_as_csv()
    csv_rows = list(csv_data)
    
    # Data structures
    reagents = {}
    reagent_pause = {}
    reagent_mix_after = {}
    reagent_mix_before = {}
    
    # Find the header row with column numbers
    header_row_idx = -1
    volume_col_start = -1
    
    for idx, row in enumerate(csv_rows):
        if len(row) > 3:
            # Look for row with "Volume (ul)" and numbered columns
            if 'Volume (ul)' in str(row):
                header_row_idx = idx
                # Find where the numbered columns start
                for col_idx, cell in enumerate(row):
                    try:
                        if float(str(cell).strip()) == 1.0:
                            volume_col_start = col_idx
                            break
                    except:
                        continue
                break
    
    if header_row_idx == -1 or volume_col_start == -1:
        protocol.comment("ERROR: Could not find volume data structure in CSV")
        return
    
    # Find reagent name from the row before header
    current_reagent = None
    if header_row_idx > 0:
        for cell in csv_rows[header_row_idx - 1]:
            cell_str = str(cell).strip()
            if 'Reagent Unique Name:' in cell_str:
                parts = cell_str.split(':')
                if len(parts) > 1 and parts[1].strip():
                    current_reagent = parts[1].strip()
                    reagents[current_reagent] = {}
                    break
    
    if not current_reagent:
        protocol.comment("ERROR: Could not find reagent name")
        return
    
    # Parse volume data rows (A-H)
    for row_idx in range(header_row_idx + 1, min(header_row_idx + 9, len(csv_rows))):
        if row_idx >= len(csv_rows):
            break
        row = csv_rows[row_idx]
        if len(row) == 0:
            continue
        
        # Find the row letter
        row_letter = None
        for cell in row:
            cell_str = str(cell).strip()
            if cell_str in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
                row_letter = cell_str
                break
        
        if not row_letter:
            continue
        
        # Extract volumes from the numbered columns
        for col_offset in range(12):
            col_idx = volume_col_start + col_offset
            if col_idx < len(row):
                try:
                    volume = float(row[col_idx])
                    if volume > 0:
                        well_name = f"{row_letter}{col_offset + 1}"
                        reagents[current_reagent][well_name] = volume
                except (ValueError, TypeError):
                    continue
    
    # Parse pause settings - look for rows with reagent names and Yes/No
    for row in csv_rows:
        if len(row) > 1:
            for col_idx in range(len(row) - 1):
                cell_val = str(row[col_idx]).strip()
                next_val = str(row[col_idx + 1]).strip().upper()
                if cell_val == current_reagent and next_val in ['YES', 'NO']:
                    reagent_pause[current_reagent] = (next_val == 'YES')
                    break
    
    # Parse mix after settings - look for "Mix Each Well" section
    in_mix_section = False
    for row in csv_rows:
        if len(row) > 0:
            first_cell = str(row[0]).strip()
            if 'Mix  Each Well' in first_cell or 'Mix Each Well' in first_cell:
                in_mix_section = True
                continue
            if in_mix_section and len(row) > 1:
                try:
                    rname = str(row[0]).strip()
                    mixes = int(float(row[1]))
                    if rname and rname in reagents:
                        reagent_mix_after[rname] = mixes
                except:
                    continue
    
    # Parse mix before settings - look for "Mix the Reagents Before" section
    in_mix_before_section = False
    for row in csv_rows:
        if len(row) > 0:
            first_cell = str(row[0]).strip()
            if 'Mix the Reagents Before' in first_cell:
                in_mix_before_section = True
                continue
            if in_mix_before_section and len(row) > 3:
                try:
                    rname = str(row[0]).strip()
                    mix_start = int(float(row[1]))
                    mix_interval = int(float(row[2]))
                    mix_during = int(float(row[3]))
                    if rname and rname in reagents:
                        reagent_mix_before[rname] = {
                            'start': mix_start,
                            'interval': mix_interval,
                            'times': mix_during
                        }
                except:
                    continue
    
    # Keep only the first num_reagents
    reagent_list = list(reagents.keys())[:num_reagents]
    
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
        protocol.comment(f"  Wells to fill: {list(reagents[reagent_name].keys())}")
        protocol.comment(f"  Pause before: {'Yes' if pause else 'No'}")
        protocol.comment(f"  Mix in well: {mix_after} times")
        protocol.comment(f"  Mix at start: {mix_before['start']} times")
        if mix_before['interval'] > 0:
            protocol.comment(f"  Mix every {mix_before['interval']} samples: {mix_before['times']} times")
    protocol.comment("=" * 60)
    
    # ============================================================================
    # LABWARE LOADING
    # ============================================================================
    reagent_rack = protocol.load_labware(
        'opentrons_24_aluminumblock_nest_1.5ml_snapcap',
        1,
        'Reagent Tubes'
    )
    dest_plate = protocol.load_labware(
        'opentrons_96_wellplate_200ul_pcr_full_skirt',
        2,
        'Destination Plate'
    )
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 4)
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 5)
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
    
    # Track cumulative volume in each well
    well_total_volumes = {}
    
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
        
        if reagent_pause.get(reagent_name, False):
            protocol.pause(f"Please add {reagent_name} to tube and click Resume")
        
        protocol.comment(f"\nDispensing {reagent_name}...")
        source_tube = reagent_tubes[reagent_name]
        wells_to_fill = reagents[reagent_name]
        
        mix_after = reagent_mix_after.get(reagent_name, 0)
        mix_before = reagent_mix_before.get(reagent_name, {'start': 0, 'interval': 0, 'times': 0})
        
        p20.pick_up_tip()
        
        if mix_before['start'] > 0:
            protocol.comment(f"  Mixing {reagent_name} in tube {mix_before['start']} times")
            p20.mix(mix_before['start'], 15, source_tube.bottom(z=1))
            p20.blow_out(source_tube.top(z=-2))
        
        sample_count = 0
        for well_name, volume in wells_to_fill.items():
            sample_count += 1
            dest_well = dest_plate[well_name]
            
            # Update total volume for this well
            if well_name not in well_total_volumes:
                well_total_volumes[well_name] = 0
            well_total_volumes[well_name] += volume
            
            if mix_before['interval'] > 0 and sample_count % mix_before['interval'] == 0 and mix_before['times'] > 0:
                protocol.comment(f"  Mixing {reagent_name} after {sample_count} samples")
                p20.mix(mix_before['times'], 15, source_tube.bottom(z=1))
                p20.blow_out(source_tube.top(z=-2))
            
            if volume > 20:
                num_transfers = math.ceil(volume / 20)
                for i in range(num_transfers):
                    transfer_vol = min(20, volume - (i * 20))
                    p20.aspirate(transfer_vol, source_tube.bottom(z=1))
                    p20.dispense(transfer_vol, dest_well.bottom(z=1))
                    if i == num_transfers - 1:
                        p20.blow_out(dest_well.top(z=-2))
            else:
                p20.aspirate(volume, source_tube.bottom(z=1))
                p20.dispense(volume, dest_well.bottom(z=1))
                p20.blow_out(dest_well.top(z=-2))
            
            if mix_after > 0:
                # Mix based on TOTAL volume in well
                total_vol = well_total_volumes[well_name]
                mix_volume = max(2, min(total_vol * 0.8, 18))
                p20.mix(mix_after, mix_volume, dest_well.bottom(z=0.5))
                p20.blow_out(dest_well.top(z=-2))
        
        p20.drop_tip()
        protocol.comment(f"  Completed {len(wells_to_fill)} wells")
    
    protocol.comment("=" * 60)
    protocol.comment("PROTOCOL COMPLETE!")
    protocol.comment(f"Total reagents dispensed: {len(reagent_list)}")
    protocol.comment("=" * 60)
