from opentrons import protocol_api

metadata = {
    'protocolName': 'Multiple Plate Dilutions with Runtime Parameters',
    'author': 'OpentronsAI',
    'description': 'Dilute samples from multiple plates with user-specified plate counts',
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
        description="CSV with 6 columns (see instructions and template)"
        # source_plate, source_well, destination_plate, destination_well, sample_volume, water_volume, initial_sample_volume"
    )
    
    # Add parameter for number of source plates
    parameters.add_int(
        variable_name="num_source_plates",
        display_name="Number of Source Plates",
        description="How many source plates to use (1-5)",
        default=3,
        minimum=1,
        maximum=5
    )
    
    # Add parameter for number of destination plates
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
    csv_data = protocol.params.multiple_plate_dilution_data.parse_as_csv()
    
    # Convert CSV to list of dictionaries for easier column access
    csv_rows = list(csv_data)
    headers = csv_rows[0]
    well_data = [dict(zip(headers, row)) for row in csv_rows[1:]]  # convert rows to dict

    # Normalize 'source_plate' and 'destination_plate' values to integers
    protocol.comment(f\"Raw CSV rows received: {well_data}\")
    for row in well_data:
        row['source_plate'] = int(float(row['source_plate']))
        row['destination_plate'] = int(float(row['destination_plate']))

    # ============================================================================
    # VALIDATION SECTION - Check all plate numbers before proceeding
    # ============================================================================
    protocol.comment("=" * 60)
    protocol.comment("VALIDATION: Checking CSV data against loaded plates")
    protocol.comment("=" * 60)
    
    # Track validation errors
    validation_errors = []
    
    # Track which plates are actually needed from CSV
    required_source_plates = set()
    required_destination_plates = set()
    
    for idx, row in enumerate(well_data):
        row_number = idx + 2  # +2 because row 1 is header, and we're 0-indexed
        
        try:
            source_plate_num = int(row['source_plate'])
            dest_plate_num = int(row['destination_plate'])
        except (ValueError, KeyError) as e:
            validation_errors.append(f"Row {row_number}: Invalid plate number format - {str(e)}")
            continue
        
        required_source_plates.add(source_plate_num)
        required_destination_plates.add(dest_plate_num)
        
        # Check if source plate number exceeds loaded plates
        if source_plate_num > num_source_plates:
            validation_errors.append(
                f"Row {row_number}: Source plate {source_plate_num} is not loaded. "
                f"Only {num_source_plates} source plate(s) available."
            )
        
        # Check if source plate number is less than 1
        if source_plate_num < 1:
            validation_errors.append(
                f"Row {row_number}: Source plate {source_plate_num} is invalid. "
                f"Plate numbers must be >= 1."
            )
        
        # Check if destination plate number exceeds loaded plates
        if dest_plate_num > num_destination_plates:
            validation_errors.append(
                f"Row {row_number}: Destination plate {dest_plate_num} is not loaded. "
                f"Only {num_destination_plates} destination plate(s) available."
            )
        
        # Check if destination plate number is less than 1
        if dest_plate_num < 1:
            validation_errors.append(
                f"Row {row_number}: Destination plate {dest_plate_num} is invalid. "
                f"Plate numbers must be >= 1."
            )
    
    # Display validation summary
    protocol.comment("-" * 60)
    protocol.comment(f"Source plates required by CSV: {sorted(required_source_plates)}")
    protocol.comment(f"Source plates loaded: {list(range(1, num_source_plates + 1))}")
    protocol.comment(f"Destination plates required by CSV: {sorted(required_destination_plates)}")
    protocol.comment(f"Destination plates loaded: {list(range(1, num_destination_plates + 1))}")
    protocol.comment("-" * 60)
    
    # If there are validation errors, stop the protocol
    if validation_errors:
        protocol.comment("VALIDATION FAILED - Errors found in CSV:")
        protocol.comment("-" * 60)
        for error in validation_errors:
            protocol.comment(error)
        protocol.comment("-" * 60)
        protocol.comment(f"Total errors found: {len(validation_errors)}")
        protocol.comment("")
        protocol.comment("Please fix your CSV file to match the loaded plates:")
        protocol.comment(f"  - Source plates available: 1 to {num_source_plates}")
        protocol.comment(f"  - Destination plates available: 1 to {num_destination_plates}")
        protocol.comment("")
        raise ValueError(
            f"CSV validation failed with {len(validation_errors)} error(s). "
            f"Please fix your CSV file and try again. See protocol comments for details."
        )
    
    # If validation passes, continue
    protocol.comment("SUCCESS: All CSV rows reference valid plate numbers")
    protocol.comment("=" * 60)
    
    # Calculate total water volume needed
    total_water_volume = sum(float(row['water_volume']) for row in well_data)
    total_water_volume_with_buffer = total_water_volume + 100
    
    protocol.comment(f"Total water volume needed: {total_water_volume:.1f} µL")
    protocol.comment(f"Total water volume with buffer: {total_water_volume_with_buffer:.1f} µL")
    protocol.comment(f"Please ensure at least {total_water_volume_with_buffer:.1f} µL of water is in well A1")
    
    # ============================================================================
    # LABWARE LOADING SECTION
    # ============================================================================
    
    # Load water reservoir
    water_reservoir = protocol.load_labware('opentrons_24_aluminumblock_nest_1.5ml_snapcap', 1, 'Water Reservoir: 1.5 mL tube in aluminum block')
    
    # Dynamically load source plates based on user input
    source_plates = {}
    source_slots = [3, 4, 5, 6, 7]  # Maximum 5 source plates
    for i in range(num_source_plates):
        plate_num = str(i + 1)
        source_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            source_slots[i],
            f'Source PCR Plate {plate_num}'
        )
    
    # Dynamically load destination plates based on user input
    destination_plates = {}
    destination_slots = [8, 9, 10]  # Maximum 3 destination plates
    for i in range(num_destination_plates):
        plate_num = str(i + 1)
        destination_plates[plate_num] = protocol.load_labware(
            'opentrons_96_wellplate_200ul_pcr_full_skirt',
            destination_slots[i],
            f'Destination Plate {plate_num}'
        )
    
    # Load tip racks
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 2)
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 11)
    
    # Load pipette
    p20_single = protocol.load_instrument('p20_single_gen2', 'right', tip_racks=[tips_20_1, tips_20_2])

    # Define reagent locations
    water_well = water_reservoir['A1']

    # Define liquids
    water = protocol.define_liquid(
        name="Nuclease Free Water", 
        description="Nuclease free water for dilutions",
        display_color="#0066FF"
    )
    
    # Load liquid into water reservoir
    water_well.load_liquid(liquid=water, volume=total_water_volume_with_buffer)
    
    protocol.comment(f"Starting protocol with {num_source_plates} source plate(s) and {num_destination_plates} destination plate(s)")
    protocol.comment(f"Processing {len(well_data)} transfers")
   
    # ============================================================================
    # STEP 1: Add water to each destination well
    # ============================================================================
    protocol.comment("Step 1: Adding water to destination wells")
    
    p20_single.pick_up_tip()
    
    for row in well_data:
        destination_plate_number = row['destination_plate']
        destination_well = row['destination_well']
        water_volume = float(row['water_volume'])
        
        destination_plate = destination_plates[destination_plate_number]
        
        # Transfer water using the same tip
        p20_single.transfer(
            water_volume,
            water_well,
            destination_plate[destination_well],
            rate=0.3,
            touch_tip=True,
            blow_out=True,
            blowout_location='destination well',
            air_gap=1,
            new_tip='never'
        )
    
    p20_single.drop_tip()
    protocol.comment("Step 1 complete: Water added to all destination wells")

    # ============================================================================
    # STEP 2: Add samples to destination wells
    # ============================================================================
    protocol.comment("Step 2: Adding samples to destination wells")
    
    for row in well_data:
        source_plate_number = row['source_plate']
        source_well = row['source_well']
        destination_plate_number = row['destination_plate']
        destination_well = row['destination_well']
        sample_volume = float(row['sample_volume'])
        initial_sample_volume = float(row['initial_sample_volume'])
        water_volume = float(row['water_volume'])
        
        source_plate = source_plates[source_plate_number]
        destination_plate = destination_plates[destination_plate_number]
        
        # Calculate mixing volumes based on actual volumes
        # Mix before: use 80% of initial sample volume, max 20 µL
        mix_before_volume = min(initial_sample_volume * 0.8, 20)
        
        # Mix after: use 80% of final volume (sample + water), max 20 µL
        final_volume = sample_volume + water_volume
        mix_after_volume = min(final_volume * 0.8, 20)
        
        # Transfer sample with mixing
        p20_single.transfer(
            sample_volume,
            source_plate[source_well],
            destination_plate[destination_well],
            mix_before=(10, .8 * initial_sample_volume),
            mix_after=(5, mix_after_volume),
            new_tip='always',
            rate=0.3,
            touch_tip=True,
            blow_out=True,
            blowout_location='destination well',
            air_gap=1
        )
    
    protocol.comment("Step 2 complete: Samples added to all destination wells")
    protocol.comment("=" * 60)
    protocol.comment("Protocol complete! All steps finished successfully.")
    protocol.comment(f"Total transfers completed: {len(well_data)}")
    protocol.comment("=" * 60)