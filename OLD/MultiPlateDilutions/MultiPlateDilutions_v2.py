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
    )
    
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
    
    # Convert CSV to list, skipping header row
    csv_rows = list(csv_data)
    headers = csv_rows[0]
    
    # Process each row and create a clean data structure
    well_data = []
    for row in csv_rows[1:]:  # Skip header
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
            protocol.comment(f"Error details: {str(e)}")
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
    
    for idx, row in enumerate(well_data):
        row_number = idx + 2  # +2 because row 1 is header
        
        source_plate_num = row['source_plate']
        dest_plate_num = row['destination_plate']
        
        required_source_plates.add(source_plate_num)
        required_destination_plates.add(dest_plate_num)
        
        # Validate source plate number
        if source_plate_num < 1 or source_plate_num > num_source_plates:
            validation_errors.append(
                f"Row {row_number}: Source plate {source_plate_num} is invalid. "
                f"Must be between 1 and {num_source_plates}."
            )
        
        # Validate destination plate number
        if dest_plate_num < 1 or dest_plate_num > num_destination_plates:
            validation_errors.append(
                f"Row {row_number}: Destination plate {dest_plate_num} is invalid. "
                f"Must be between 1 and {num_destination_plates}."
            )
        
        # Validate volumes
        if row['sample_volume'] <= 0:
            validation_errors.append(
                f"Row {row_number}: Sample volume must be greater than 0"
            )
        
        if row['water_volume'] < 0:
            validation_errors.append(
                f"Row {row_number}: Water volume cannot be negative"
            )
        
        if row['initial_sample_volume'] <= 0:
            validation_errors.append(
                f"Row {row_number}: Initial sample volume must be greater than 0"
            )
    
    # Display validation summary
    protocol.comment("-" * 60)
    protocol.comment(f"Source plates required: {sorted(required_source_plates)}")
    protocol.comment(f"Source plates loaded: {list(range(1, num_source_plates + 1))}")
    protocol.comment(f"Destination plates required: {sorted(required_destination_plates)}")
    protocol.comment(f"Destination plates loaded: {list(range(1, num_destination_plates + 1))}")
    protocol.comment("-" * 60)
    
    # Stop if validation fails
    if validation_errors:
        protocol.comment("VALIDATION FAILED - Errors found:")
        protocol.comment("-" * 60)
        for error in validation_errors:
            protocol.comment(error)
        protocol.comment("-" * 60)
        raise ValueError(
            f"CSV validation failed with {len(validation_errors)} error(s). "
            f"See protocol comments for details."
        )
    
    protocol.comment("SUCCESS: All CSV rows validated")
    protocol.comment("=" * 60)
    
    # Calculate total water volume
    total_water_volume = sum(row['water_volume'] for row in well_data)
    total_water_volume_with_buffer = total_water_volume + 100
    
    protocol.comment(f"Total water needed: {total_water_volume:.1f} µL")
    protocol.comment(f"With buffer: {total_water_volume_with_buffer:.1f} µL")
    
    # ============================================================================
    # LABWARE LOADING
    # ============================================================================
    
    # Load water reservoir
    water_reservoir = protocol.load_labware(
        'opentrons_24_aluminumblock_nest_1.5ml_snapcap', 
        9, 
        'Water Reservoir'
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
    
    water_well.load_liquid(liquid=water, volume=total_water_volume_with_buffer)
    
    protocol.comment(f"Starting protocol with {num_source_plates} source plate(s)")
    protocol.comment(f"and {num_destination_plates} destination plate(s)")
    protocol.comment(f"Processing {len(well_data)} transfers")
   
    # ============================================================================
    # STEP 1: Add water to destination wells
    # ============================================================================
    protocol.comment("Step 1: Adding water to destination wells")
    
    p20_single.pick_up_tip()

    for row in well_data:
        destination_plate = destination_plates[row['destination_plate']]
        dest_well = destination_plate[row['destination_well']]
        
        # Aspirate water
        p20_single.aspirate(row['water_volume'], water_well)
        p20_single.air_gap(1)
        
        # Dispense close to bottom for accuracy
        p20_single.dispense(row['water_volume'] + 1, dest_well.bottom(z=1), rate=0.3)
        
        # Blow out at liquid surface
        p20_single.blow_out(dest_well.top(z=-2))
        
        # Touch tip lower in the well (5mm below the top)
        p20_single.touch_tip(dest_well, v_offset=-5, speed=10)

    p20_single.drop_tip()
    
    protocol.comment("Step 1 complete: Water added to all wells")

    # ============================================================================
    # STEP 2: Add samples to destination wells
    # ============================================================================
    protocol.comment("Step 2: Adding samples to destination wells")
    
    for row in well_data:
        source_plate = source_plates[row['source_plate']]
        destination_plate = destination_plates[row['destination_plate']]
        
        source_well = source_plate[row['source_well']]
        dest_well = destination_plate[row['destination_well']]
        
        # Calculate mixing volumes - keep original 80% and 20 µL max
        mix_before_volume = min(row['initial_sample_volume'] * 0.8, 20)
        final_volume = row['sample_volume'] + row['water_volume']
        mix_after_volume = min(final_volume * 0.8, 20)

        p20_single.pick_up_tip()
        
        # Mix in source well before aspirating - position tip low in well
        p20_single.mix(10, mix_before_volume, source_well.bottom(z=0.5))
        
        # Aspirate sample from low position
        p20_single.aspirate(row['sample_volume'], source_well.bottom(z=0.5))
        p20_single.air_gap(1)
        
        # Dispense into destination well
        p20_single.dispense(row['sample_volume'] + 1, dest_well.bottom(z=1), rate=0.3)
        
        # Mix in destination well - position tip low to avoid air
        p20_single.mix(10, mix_after_volume, dest_well.bottom(z=0.5))
        
        # Blow out at liquid surface
        p20_single.blow_out(dest_well.top(z=-2))
        
        # Touch tip lower in the well (5mm below the top)
        p20_single.touch_tip(dest_well, v_offset=-5, speed=10)
        
        p20_single.drop_tip()
    
    protocol.comment("Step 2 complete: All samples transferred")
    protocol.comment("=" * 60)
    protocol.comment("Protocol complete!")
    protocol.comment(f"Total transfers: {len(well_data)}")
    protocol.comment("=" * 60)