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
    # PARSE EXCEL/CSV DATA - FOR HORIZONTAL TEMPLATE LAYOUT
    # ============================================================================
    csv_data = protocol.params.reagent_layout.parse_as_csv()
    csv_rows = list(csv_data)
    
    # Data structures
    reagents = {}
    reagent_pause = {}
    reagent_mix_after = {}
    reagent_mix_before = {}
    
    # Step 1: Find all reagent names by looking for "Reagent Unique Name:" rows
    reagent_name_rows = []
    for row_idx, row in enumerate(csv_rows):
        for col_idx, cell in enumerate(row):
            if 'Reagent Unique Name:' in str(cell):
                # Look for reagent name in adjacent cells (same row, next columns)
                for next_col in range(col_idx + 1, min(col_idx + 5, len(row))):
                    potential_name = str(row[next_col]).strip()
                    if potential_name and potential_name not in ['', 'Pause', 'Volume', 'Reagent']:
                        reagent_name_rows.append({'name': potential_name, 'row_idx': row_idx})
                        reagents[potential_name] = {}
                        protocol.comment(f"Found reagent: {potential_name} at row {row_idx}")
                        break
                break
    
    if not reagents:
        protocol.comment("ERROR: No reagents found in CSV")
        return
    
    # Step 2: Parse volume data for each reagent
    for reagent_info in reagent_name_rows:
        reagent_name = reagent_info['name']
        start_row = reagent_info['row_idx']
        
        # Find the "Volume (ul)" row for this reagent
        volume_header_row = None
        col_number_positions = {}
        
        for row_idx in range(start_row, min(start_row + 3, len(csv_rows))):
            row = csv_rows[row_idx]
            for col_idx, cell in enumerate(row):
                if 'Volume (ul)' in str(cell) or 'Volume' in str(cell):
                    volume_header_row = row_idx
                    # Map column numbers to their positions
                    for num_col_idx in range(col_idx + 1, min(col_idx + 15, len(row))):
                        try:
                            col_num = int(float(str(row[num_col_idx]).strip()))
                            if 1 <= col_num <= 12:
                                col_number_positions[col_num] = num_col_idx
                        except:
                            pass
                    break
            if volume_header_row:
                break
        
        if not volume_header_row or not col_number_positions:
            protocol.comment(f"Could not find volume data structure for {reagent_name}")
            continue
        
        # Parse volume rows (A-H) after the header
        for row_idx in range(volume_header_row + 1, min(volume_header_row + 10, len(csv_rows))):
            row = csv_rows[row_idx]
            if len(row) == 0:
                continue
            
            # Find row letter
            row_letter = None
            for cell in row:
                cell_str = str(cell).strip()
                if cell_str in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
                    row_letter = cell_str
                    break
            
            if not row_letter:
                continue
            
            # Extract volumes from mapped column positions
            for col_num in range(1, 13):
                if col_num in col_number_positions:
                    col_idx = col_number_positions[col_num]
                    if col_idx < len(row):
                        try:
                            volume = float(row[col_idx])
                            if volume > 0:
                                well_name = f"{row_letter}{col_num}"
                                reagents[reagent_name][well_name] = volume
                                protocol.comment(f"  Found {reagent_name} -> {well_name}: {volume}µL")
                        except (ValueError, TypeError):
                            pass
    
    # Step 3: Parse pause settings
    in_pause_section = False
    for row in csv_rows:
        for cell in row:
            if 'Pause Robot Before Starting' in str(cell) or 'Reagent Pause' in str(cell):
                in_pause_section = True
                break
        
        if in_pause_section and len(row) > 1:
            for col_idx in range(len(row) - 1):
                reagent_name = str(row[col_idx]).strip()
                pause_value = str(row[col_idx + 1]).strip().upper()
                
                if reagent_name in reagents and pause_value in ['YES', 'NO']:
                    reagent_pause[reagent_name] = (pause_value == 'YES')
    
    # Step 4: Parse "Mix Each Well After Adding Reagent" settings
    in_mix_after_section = False
    for row in csv_rows:
        for cell in row:
            if 'Mix  Each Well' in str(cell) or 'Mix Each Well' in str(cell):
                in_mix_after_section = True
                break
        
        if in_mix_after_section and len(row) > 1:
            for col_idx in range(len(row) - 1):
                reagent_name = str(row[col_idx]).strip()
                try:
                    mix_times = int(float(row[col_idx + 1]))
                    if reagent_name in reagents:
                        reagent_mix_after[reagent_name] = mix_times
                except:
                    pass
    
    # Step 5: Parse "Mix the Reagents Before Adding to the Wells" settings
    in_mix_before_section = False
    for row in csv_rows:
        for cell in row:
            if 'Mix the Reagents Before' in str(cell):
                in_mix_before_section = True
                break
        
        if in_mix_before_section and len(row) > 3:
            reagent_name = str(row[0]).strip()
            if reagent_name in reagents:
                try:
                    mix_start = int(float(row[1]))
                    mix_interval = int(float(row[2]))
                    mix_times = int(float(row[3]))
                    reagent_mix_before[reagent_name] = {
                        'start': mix_start,
                        'interval': mix_interval,
                        'times': mix_times
                    }
                except:
                    pass
    
    # Keep only the first num_reagents
    reagent_list = list(reagents.keys())[:num_reagents]
    
    if not reagent_list:
        protocol.comment("ERROR: No reagents with wells found")
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
        if num_wells > 0:
            protocol.comment(f"  Wells to fill: {list(reagents[reagent_name].keys())}")
        protocol.comment(f"  Pause before: {'Yes' if pause else 'No'}")
        protocol.comment(f"  Mix in well after dispense: {mix_after} times")
        protocol.comment(f"  Mix source at start: {mix_before['start']} times")
        if mix_before['interval'] > 0:
            protocol.comment(f"  Mix source every {mix_before['interval']} samples: {mix_before['times']} times")
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
    
    protocol.comment("=" * 60)
    protocol.comment("STARTING REAGENT DISPENSING")
    protocol.comment("=" * 60)
    
    # Track cumulative volume in each well
    well_total_volumes = {}
    
    # ============================================================================
    # DISPENSE REAGENTS
    # ============================================================================
    for reagent_name in reagent_list:
        protocol.comment(f"\n>>> Processing reagent: {reagent_name}")
        
        if len(reagents[reagent_name]) == 0:
            protocol.comment(f"  SKIPPING - no wells defined")
            continue
        
        protocol.comment(f"  Wells to dispense: {list(reagents[reagent_name].keys())}")
        
        if reagent_pause.get(reagent_name, False):
            protocol.pause(f"Please add {reagent_name} to tube and click Resume")
        
        source_tube = reagent_tubes[reagent_name]
        wells_to_fill = reagents[reagent_name]
        
        mix_after = reagent_mix_after.get(reagent_name, 0)
        mix_before = reagent_mix_before.get(reagent_name, {'start': 0, 'interval': 0, 'times': 0})
        
        protocol.comment(f"  Mix settings - after:{mix_after}, before:{mix_before}")
        
        # Pick up tip
        p20.pick_up_tip()
        protocol.comment(f"  Picked up tip")
        
        # Mix at start if specified
        if mix_before['start'] > 0:
            protocol.comment(f"  >>> MIXING SOURCE TUBE {mix_before['start']} times at start")
            p20.mix(mix_before['start'], 15, source_tube.bottom(z=1))
            p20.blow_out(source_tube.top(z=-2))
            protocol.comment(f"  >>> Source tube mixing complete")
        
        # Dispense to each well
        sample_count = 0
        for well_name, volume in wells_to_fill.items():
            sample_count += 1
            dest_well = dest_plate[well_name]
            
            protocol.comment(f"  Sample {sample_count}: Dispensing {volume}µL to {well_name}")
            
            # Update total volume for this well
            if well_name not in well_total_volumes:
                well_total_volumes[well_name] = 0
            well_total_volumes[well_name] += volume
            
            # Mix during dispensing if interval is reached
            if mix_before['interval'] > 0 and sample_count % mix_before['interval'] == 0 and mix_before['times'] > 0:
                protocol.comment(f"  >>> MIXING SOURCE TUBE after {sample_count} samples: {mix_before['times']} times")
                p20.mix(mix_before['times'], 15, source_tube.bottom(z=1))
                p20.blow_out(source_tube.top(z=-2))
            
            # Handle volumes that need splitting (>20µL)
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
            
            # Mix in well if specified
            if mix_after > 0:
                total_vol = well_total_volumes[well_name]
                mix_volume = max(2, min(total_vol * 0.8, 18))
                protocol.comment(f"  >>> MIXING WELL {well_name}: {mix_after} times with {mix_volume}µL (total vol={total_vol}µL)")
                p20.mix(mix_after, mix_volume, dest_well.bottom(z=0.5))
                p20.blow_out(dest_well.top(z=-2))
                protocol.comment(f"  >>> Well mixing complete")
        
        # Drop tip
        p20.drop_tip()
        protocol.comment(f"  Completed {len(wells_to_fill)} wells for {reagent_name}")
    
    protocol.comment("=" * 60)
    protocol.comment("PROTOCOL COMPLETE!")
    protocol.comment(f"Total reagents dispensed: {len(reagent_list)}")
    protocol.comment("=" * 60)
