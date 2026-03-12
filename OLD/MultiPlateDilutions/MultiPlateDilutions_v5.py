## MULTIPLE PLATE DILUTIONS V4 - WITH VOLUME SPLITTING

from opentrons import protocol_api
import math

metadata = {
    'protocolName': 'Multiple Plate Dilutions V5',
    'author': 'OpentronsAI',
    'description': 'Dilute samples from multiple plates',
    # Adds all water first
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="multiple_plate_dilution_data",
        display_name="Multiple Plate Dilution CSV",
        description="CSV with 7 columns, see template"
    )
    #Source Plate, Source Well, Dest Plate, Dest Well, Sample Vol, Water Vol, Initial Sample Vol
    
    parameters.add_int(
        variable_name="num_source_plates",
        display_name="Number of Source Plates",
        description="How many source plates to use (1-5)",
        default=3,
        minimum=1,
        maximum=5
    )
    
    parameters.add_int(
        variable_name="num_destination_plates",
        display_name="Number of Destination Plates",
        description="How many destination plates to use (1-3)",
        default=2,
        minimum=1,
        maximum=3
    )

def run(protocol: protocol_api.ProtocolContext):
    # Access runtime parameters
    num_source_plates = protocol.params.num_source_plates
    num_destination_plates = protocol.params.num_destination_plates
    
    # Parse CSV data
    csv_data = protocol.params.multiple_plate_dilution_data.parse_as_csv()
    csv_rows = list(csv_data)
    headers = csv_rows[0]
    
    # Process CSV and create data structure
    well_data = []
    for row in csv_rows[1:]:
        try:
            well_data.append({
                'source_plate': int(float(row[0])),
                'source_well': str(row[1]).strip(),
                'destination_plate': int(float(row[2])),
                'destination_well': str(row[3]).strip(),
                'sample_volume': float(row[4]),
                'water_volume': float(row[5]),
                'initial_sample_volume': float(row[6])
            })
        except (ValueError, IndexError) as e:
            protocol.comment(f"Error parsing row: {row}")
            raise ValueError(f"CSV parsing error: {str(e)}")

    protocol.comment(f"Successfully parsed {len(well_data)} rows from CSV")

    # ============================================================================
    # VALIDATION SECTION
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("VALIDATION: Checking CSV data against loaded plates")
    protocol.comment("=" * 60)
    
    validation_errors = []
    required_source_plates = set()
    required_destination_plates = set()
    
    # Categorize wells by dilution type
    wells_normal = []  # Final volume ≤ 200 µL
    wells_large_dilution = []  # Final volume > 200 µL (need reservoir prep)
    
    for idx, row in enumerate(well_data):
        row_number = idx + 2
        
        source_plate_num = row['source_plate']
        dest_plate_num = row['destination_plate']
        final_volume = row['sample_volume'] + row['water_volume']
        
        required_source_plates.add(source_plate_num)
        required_destination_plates.add(dest_plate_num)
        
        # Validate plate numbers
        if source_plate_num < 1 or source_plate_num > num_source_plates:
            validation_errors.append(
                f"Row {row_number}: Source plate {source_plate_num} invalid. "
                f"Must be 1-{num_source_plates}."
            )
        
        if dest_plate_num < 1 or dest_plate_num > num_destination_plates:
            validation_errors.append(
                f"Row {row_number}: Dest plate {dest_plate_num} invalid. "
                f"Must be 1-{num_destination_plates}."
            )
        
        # Validate volumes
        if row['sample_volume'] <= 0:
            validation_errors.append(f"Row {row_number}: Sample volume must be > 0")
        
        if row['water_volume'] < 0:
            validation_errors.append(f"Row {row_number}: Water volume cannot be negative")
        
        if row['initial_sample_volume'] <= 0:
            validation_errors.append(f"Row {row_number}: Initial sample volume must be > 0")
        
        # Categorize by final volume
        if final_volume > 200:
            wells_large_dilution.append(row)
        else:
            wells_normal.append(row)
    
    # Display validation summary
    protocol.comment("-" * 60)
    protocol.comment(f"Source plates required: {sorted(required_source_plates)}")
    protocol.comment(f"Destination plates required: {sorted(required_destination_plates)}")
    protocol.comment(f"Normal dilutions (≤200 µL): {len(wells_normal)}")
    protocol.comment(f"Large dilutions (>200 µL): {len(wells_large_dilution)}")
    protocol.comment("-" * 60)
    
    if validation_errors:
        protocol.comment("VALIDATION FAILED:")
        for error in validation_errors:
            protocol.comment(error)
        raise ValueError(f"CSV validation failed with {len(validation_errors)} error(s)")
    
    # Calculate reservoir tubes needed for large dilutions
    num_reservoir_tubes_needed = len(wells_large_dilution)
    
    if num_reservoir_tubes_needed > 0:
        protocol.comment("=" * 60)
        protocol.comment("LARGE DILUTION SETUP REQUIRED")
        protocol.comment("=" * 60)
        protocol.comment(f"Number of reservoir tubes needed: {num_reservoir_tubes_needed}")
        protocol.comment(f"These will be used in positions starting from B1")
        protocol.comment("Please ensure water reservoir has sufficient tubes loaded")
        protocol.comment("=" * 60)
    
    # Further categorize normal wells by water volume
    wells_water_first = [row for row in wells_normal if row['water_volume'] >= 5]
    wells_water_after = [row for row in wells_normal if row['water_volume'] < 5]
    
    protocol.comment(f"Normal dilutions - water first (≥5 µL): {len(wells_water_first)}")
    protocol.comment(f"Normal dilutions - water after (<5 µL): {len(wells_water_after)}")
    
    # ============================================================================
    # TIP CALCULATION
    # ============================================================================
    total_tips_needed = 0
    
    # Large dilutions: 1 tip for all reservoir water + 1 tip per dilution (sample + mix + 50µL transfer)
    if wells_large_dilution:
        total_tips_needed += 1  # One tip for all reservoir water
        total_tips_needed += len(wells_large_dilution)  # One tip per dilution (sample + mix + transfer)
    
    # Water first: 1 tip for all plate water additions + 1 tip per sample
    if wells_water_first:
        total_tips_needed += 1  # One tip for all plate water
        total_tips_needed += len(wells_water_first)  # One tip per sample
    
    # Water after: 1 tip per sample + 1 tip per water addition
    total_tips_needed += len(wells_water_after) * 2
    
    tips_per_rack = 96
    tip_racks_needed = math.ceil(total_tips_needed / tips_per_rack)
    
    protocol.comment("=" * 60)
    protocol.comment("TIP USAGE CALCULATION")
    protocol.comment("=" * 60)
    protocol.comment(f"Total tips needed: {total_tips_needed}")
    protocol.comment(f"Tip racks required: {tip_racks_needed}")
    if tip_racks_needed == 1:
        protocol.comment("You only need 1 tip rack for this protocol")
    else:
        protocol.comment(f"You need {tip_racks_needed} tip racks for this protocol")
    protocol.comment("=" * 60)
    
    # Calculate total water needed
    total_water_normal = sum(row['water_volume'] for row in wells_normal)
    total_water_large = sum(row['water_volume'] for row in wells_large_dilution)
    total_water = total_water_normal + total_water_large
    total_water_with_buffer = total_water + 50
    
    protocol.comment(f"Total water needed: {total_water:.1f} µL")
    protocol.comment(f"With buffer: {total_water_with_buffer:.1f} µL")
    
    # ============================================================================
    # LABWARE LOADING
    # ============================================================================
    
    # Load water reservoir (24-tube rack for both water and large dilution prep)
    water_reservoir = protocol.load_labware(
        'opentrons_24_aluminumblock_nest_1.5ml_snapcap', 
        9, 
        'Water Reservoir & Large Dilution Prep'
    )
    
    # Load source plates
    source_plates = {}
    source_slots = [4, 5, 6, 7, 8]
    for i in range(num_source_plates):
        plate_num = i + 1
        source_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            source_slots[i],
            f'Source Plate {plate_num}'
        )
    
    # Load destination plates
    destination_plates = {}
    destination_slots = [1, 2, 3]
    for i in range(num_destination_plates):
        plate_num = i + 1
        destination_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            destination_slots[i],
            f'Destination Plate {plate_num}'
        )
    
    # Load tip racks
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 10)
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 11)
    
    # Load pipette
    p20_single = protocol.load_instrument(
        'p20_single_gen2', 
        'right', 
        tip_racks=[tips_20_1, tips_20_2]
    )

    # Define water well
    water_well = water_reservoir['A1']

    # Define and load liquids
    water = protocol.define_liquid(
        name="Nuclease Free Water", 
        description="Nuclease free water for dilutions",
        display_color="#0066FF"
    )
    
    water_well.load_liquid(liquid=water, volume=total_water_with_buffer)
    
    protocol.comment("=" * 60)
    protocol.comment("STARTING PROTOCOL")
    protocol.comment("=" * 60)
   
    # ============================================================================
    # STEP 1: Add ALL water to reservoir tubes (for large dilutions)
    # ============================================================================
    if wells_large_dilution:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 1A: Adding water to {len(wells_large_dilution)} reservoir tubes")
        protocol.comment("=" * 60)
        
        # Pick up ONE tip for all reservoir water additions
        p20_single.pick_up_tip()
        
        # Add water to all reservoir tubes
        for idx, row in enumerate(wells_large_dilution):
            # Use tubes starting from B1 (A1 is water source)
            tube_index = idx + 1
            reservoir_tube = water_reservoir.wells()[tube_index]
            
            final_volume = row['sample_volume'] + row['water_volume']
            
            protocol.comment(f"Adding water to reservoir tube {idx + 1}/{len(wells_large_dilution)}")
            protocol.comment(f"  Final volume: {final_volume:.1f} µL in tube {reservoir_tube.well_name}")
            
            # Add water to reservoir tube (split if needed)
            water_vol = row['water_volume']

            if water_vol > 19:
                num_transfers = math.ceil(water_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = water_vol - (i * 19)
                    else:
                        transfer_vol = 19

                    p20_single.aspirate(transfer_vol, water_well)
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, reservoir_tube.bottom(z=1))
                    else:
                        p20_single.dispense(transfer_vol, reservoir_tube.bottom(z=1), rate = 0.9)
                    p20_single.blow_out(reservoir_tube.bottom(z=2))
                    p20_single.blow_out(reservoir_tube.top(z=-2))
            else:
                p20_single.aspirate(water_vol, water_well)
                if water_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(water_vol + 0.5, reservoir_tube.bottom(z=1), rate=0.9)
                else:
                    p20_single.dispense(water_vol, reservoir_tube.bottom(z=1), rate=0.9)
                p20_single.blow_out(reservoir_tube.bottom(z=2))
                p20_single.blow_out(reservoir_tube.top(z=-2))

        # Drop the tip after all reservoir water additions
        p20_single.drop_tip()
        protocol.comment("Reservoir water additions complete")

    # ============================================================================
    # STEP 2: Add ALL water to destination plates (for normal dilutions with water ≥5 µL)
    # ============================================================================
    if wells_water_first:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 1B: Adding water to {len(wells_water_first)} destination plate wells")
        protocol.comment("=" * 60)
        
        # Pick up ONE tip for all plate water additions
        p20_single.pick_up_tip()

        for row in wells_water_first:
            destination_plate = destination_plates[row['destination_plate']]
            dest_well = destination_plate[row['destination_well']]
            water_vol = row['water_volume']
            
            # Split water transfer if needed
            if water_vol > 19:
                num_transfers = math.ceil(water_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = water_vol - (i * 19)
                    else:
                        transfer_vol = 19
                    
                    p20_single.aspirate(transfer_vol, water_well)
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, dest_well.bottom(z=1), rate=0.9)
                    else:
                        p20_single.dispense(transfer_vol, dest_well.bottom(z=1), rate=0.9)
                    p20_single.blow_out(dest_well.bottom(z=2))
                    p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                    p20_single.blow_out(dest_well.top(z=-2))
            else:
                p20_single.aspirate(water_vol, water_well)
                if water_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(water_vol + 0.5, dest_well.bottom(z=1), rate=0.3)
                else:
                    p20_single.dispense(water_vol, dest_well.bottom(z=1), rate=0.3)
                p20_single.blow_out(dest_well.bottom(z=2))
                p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                p20_single.blow_out(dest_well.top(z=-2))

        # Drop the tip after all plate water additions
        p20_single.drop_tip()
        protocol.comment("Plate water additions complete")

    # ============================================================================
    # STEP 3: Add samples to reservoir tubes and transfer to destination (large dilutions)
    # ============================================================================
    if wells_large_dilution:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 2: Processing {len(wells_large_dilution)} large dilutions")
        protocol.comment("=" * 60)
        
        # Now add samples, mix, and transfer 50µL - all with ONE tip per dilution
        for idx, row in enumerate(wells_large_dilution):
            tube_index = idx + 1
            reservoir_tube = water_reservoir.wells()[tube_index]
            
            source_plate = source_plates[row['source_plate']]
            source_well = source_plate[row['source_well']]
            
            destination_plate = destination_plates[row['destination_plate']]
            dest_well = destination_plate[row['destination_well']]
            
            final_volume = row['sample_volume'] + row['water_volume']
            
            protocol.comment(f"Processing dilution {idx + 1}/{len(wells_large_dilution)}")
            
            # Pick up ONE tip for this entire dilution (sample + mix + transfer)
            p20_single.pick_up_tip()
            
            # Add sample to reservoir tube (split if needed)
            sample_vol = row['sample_volume']
            mix_before_volume = min(row['initial_sample_volume'] * 0.8, 20)
            mix_after_volume = min(final_volume * 0.8, 20)

            if sample_vol > 19:
                num_transfers = math.ceil(sample_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = sample_vol - (i * 19)
                    else:
                        transfer_vol = 19
                    
                    # Mix sample before only on first transfer
                    if i == 0:
                        p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                    
                    p20_single.aspirate(transfer_vol, source_well.bottom(z=0.5))
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, reservoir_tube.bottom(z=1))
                    else:
                        p20_single.dispense(transfer_vol, reservoir_tube.bottom(z=1))
                    
                    # Mix sample + water only after the last transfer
                    if i == num_transfers - 1:
                        p20_single.mix(10, mix_after_volume, reservoir_tube.bottom(z=0.5))
        
            else:
                p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                p20_single.aspirate(sample_vol, source_well.bottom(z=0.5))
                if sample_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(sample_vol + 0.5, reservoir_tube.bottom(z=1))
                else:
                    p20_single.dispense(sample_vol, reservoir_tube.bottom(z=1))
                p20_single.mix(10, mix_after_volume, reservoir_tube.bottom(z=0.5))
            
            # Transfer 50 µL from reservoir tube to destination plate (using same tip)
            protocol.comment(f"  Transferring 50 µL to destination {row['destination_well']}")
            
            # First 19 µL
            p20_single.aspirate(19, reservoir_tube.bottom(z=0.5))
            p20_single.air_gap(0.5)
            p20_single.dispense(19.5, dest_well.bottom(z=1))
            p20_single.blow_out(dest_well.top(z=-2))
            
            # Second 19 µL
            p20_single.aspirate(19, reservoir_tube.bottom(z=0.5))
            p20_single.air_gap(0.5)
            p20_single.dispense(19.5, dest_well.bottom(z=1))
            p20_single.blow_out(dest_well.top(z=-2))
            
            # Final 12 µL
            p20_single.aspirate(12, reservoir_tube.bottom(z=0.5))
            p20_single.air_gap(0.5)
            p20_single.dispense(12.5, dest_well.bottom(z=1))
            p20_single.blow_out(dest_well.bottom(z=2))
            p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
            p20_single.blow_out(dest_well.top(z=-2))
            
            # Drop tip after completing this dilution
            p20_single.drop_tip()
        
        protocol.comment("Large dilutions complete")

    # ============================================================================
    # STEP 4: Add samples to normal wells with water volume ≥5 µL
    # ============================================================================
    if wells_water_first:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 3: Adding samples to {len(wells_water_first)} wells (water added first)")
        protocol.comment("=" * 60)
        
        for row in wells_water_first:
            source_plate = source_plates[row['source_plate']]
            destination_plate = destination_plates[row['destination_plate']]
            
            source_well = source_plate[row['source_well']]
            dest_well = destination_plate[row['destination_well']]
            
            sample_vol = row['sample_volume']
            mix_before_volume = min(row['initial_sample_volume'] * 0.8, 20)
            final_volume = row['sample_volume'] + row['water_volume']
            mix_after_volume = min(final_volume * 0.8, 20)

            p20_single.pick_up_tip()
            
            # Split sample transfer if needed
            if sample_vol > 19:
                num_transfers = math.ceil(sample_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = sample_vol - (i * 19)
                    else:
                        transfer_vol = 19
                    
                    # Mix before only on first transfer
                    if i == 0:
                        p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                    
                    p20_single.aspirate(transfer_vol, source_well.bottom(z=0.5))
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, dest_well.bottom(z=1), rate=0.5)
                    else:
                        p20_single.dispense(transfer_vol, dest_well.bottom(z=1), rate=0.5)
                    
                    # Mix after only on last transfer
                    if i == num_transfers - 1:
                        p20_single.mix(10, mix_after_volume, dest_well.bottom(z=0.5))
                    
                    p20_single.blow_out(dest_well.bottom(z=2))
                    p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                    p20_single.blow_out(dest_well.top(z=-2))
            else:
                p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                p20_single.aspirate(sample_vol, source_well.bottom(z=0.5))
                if sample_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(sample_vol + 0.5, dest_well.bottom(z=1), rate=0.3)
                else:
                    p20_single.dispense(sample_vol, dest_well.bottom(z=1), rate=0.3)
                p20_single.mix(9, mix_after_volume, dest_well.bottom(z=0.5))
                p20_single.aspirate(mix_after_volume, dest_well.bottom(z=0.5))
                p20_single.dispense(mix_after_volume, dest_well.bottom(z=0.5), rate=0.3)
                p20_single.blow_out(dest_well.bottom(z=2))
                p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                p20_single.blow_out(dest_well.top(z=-2))
                
            p20_single.drop_tip()

    # ============================================================================
    # STEP 5: Add samples FIRST to normal wells with water volume <5 µL
    # ============================================================================
    if wells_water_after:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 4: Adding samples FIRST to {len(wells_water_after)} wells (<5 µL water)")
        protocol.comment("=" * 60)
        
        for row in wells_water_after:
            source_plate = source_plates[row['source_plate']]
            destination_plate = destination_plates[row['destination_plate']]
            
            source_well = source_plate[row['source_well']]
            dest_well = destination_plate[row['destination_well']]
            
            sample_vol = row['sample_volume']
            mix_before_volume = min(row['initial_sample_volume'] * 0.8, 20)

            p20_single.pick_up_tip()

            # Split sample transfer if needed
            if sample_vol >19:
                num_transfers = math.ceil(sample_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = sample_vol - (i * 19)
                    else:
                        transfer_vol = 19
                    
                    # Mix before only on first transfer
                    if i == 0:
                        p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                    
                    p20_single.aspirate(transfer_vol, source_well.bottom(z=0.5))
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, dest_well.bottom(z=1), rate=0.5)
                    else:
                        p20_single.dispense(transfer_vol, dest_well.bottom(z=1), rate=0.5)
                    p20_single.blow_out(dest_well.bottom(z=2))
                    p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                    p20_single.blow_out(dest_well.top(z=-2))
    
            else:
                p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
                p20_single.aspirate(sample_vol, source_well.bottom(z=0.5))
                if sample_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(sample_vol + 0.5, dest_well.bottom(z=1), rate=0.5)
                else:
                    p20_single.dispense(sample_vol, dest_well.bottom(z=1), rate=0.5)
                p20_single.blow_out(dest_well.bottom(z=2))
                p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                p20_single.blow_out(dest_well.top(z=-2))
            
            p20_single.drop_tip()

    # ============================================================================
    # STEP 6: Add water AFTER samples to normal wells with water volume <5 µL
    # ============================================================================
    if wells_water_after:
        protocol.comment("=" * 60)
        protocol.comment(f"STEP 5: Adding water AFTER samples to {len(wells_water_after)} wells (<5 µL)")
        protocol.comment("=" * 60)

        for row in wells_water_after:
            destination_plate = destination_plates[row['destination_plate']]
            dest_well = destination_plate[row['destination_well']]
            
            water_vol = row['water_volume']
            final_volume = row['sample_volume'] + row['water_volume']
            mix_after_volume = min(final_volume * 0.8, 20)
            
            p20_single.pick_up_tip()

            # Split water transfer if needed
            if water_vol > 19:
                num_transfers = math.ceil(water_vol / 19)
                for i in range(num_transfers):
                    if i == num_transfers - 1:
                        transfer_vol = water_vol - (i * 19)
                    else:
                        transfer_vol = 19
                    
                    p20_single.aspirate(transfer_vol, water_well)
                    if transfer_vol >= 0.5:
                        p20_single.air_gap(0.5)
                        p20_single.dispense(transfer_vol + 0.5, dest_well.bottom(z=1))
                    else:
                        p20_single.dispense(transfer_vol, dest_well.bottom(z=1))
                    
                    # Mix after only on last transfer
                    if i == num_transfers - 1:
                        p20_single.mix(9, mix_after_volume, dest_well.bottom(z=0.5))
                        p20_single.aspirate(mix_after_volume, dest_well.bottom(z=1))
                        p20_single.dispense(mix_after_volume, dest_well.bottom(z=1), rate=0.5)
                    
                    p20_single.blow_out(dest_well.bottom(z=2))
                    p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                    p20_single.blow_out(dest_well.top(z=-2))
               
            else:
                p20_single.aspirate(water_vol, water_well)
                if water_vol >= 0.5:
                    p20_single.air_gap(0.5)
                    p20_single.dispense(water_vol + 0.5, dest_well.bottom(z=1))
                else:
                    p20_single.dispense(water_vol, dest_well.bottom(z=1))
                p20_single.mix(9, mix_after_volume, dest_well.bottom(z=0.5))
                p20_single.aspirate(mix_after_volume, dest_well.bottom(z=1))
                p20_single.dispense(mix_after_volume, dest_well.bottom(z=1), rate=0.5)
                p20_single.blow_out(dest_well.bottom(z=2))
                p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
                p20_single.blow_out(dest_well.top(z=-2))

            p20_single.drop_tip()

    # ============================================================================
    # PROTOCOL COMPLETE
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("PROTOCOL COMPLETE!")
    protocol.comment(f"Total transfers: {len(well_data)}")
    protocol.comment(f"  - Normal dilutions (water first): {len(wells_water_first)}")
    protocol.comment(f"  - Normal dilutions (water after): {len(wells_water_after)}")
    protocol.comment(f"  - Large dilutions (via reservoir): {len(wells_large_dilution)}")
    if wells_large_dilution:
        protocol.comment(f"  - Reservoir tubes used: {len(wells_large_dilution)}")
    protocol.comment("=" * 60)
    