# Need to add:
    # Proper mixing amount based on sample size input
    # Tip tap/blow

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
        description="CSV with columns: source_plate, source_well, destination_plate, destination_well, sample_volume, water_volume"
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
    
    # Convert CSV to list of dictionaries for easier access by column name
    csv_rows = list(csv_data)
    headers = csv_rows[0]
    well_data = csv_rows[1:]  # Skip header row
    
    # Load water reservoir
    water_reservoir = protocol.load_labware('nest_12_reservoir_15ml', 11, 'Water Reservoir')
    
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
    tips_20_1 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 1)
    tips_20_2 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 2)
    
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
    water_well.load_liquid(liquid=water, volume=10000)
    
    protocol.comment(f"Starting protocol with {num_source_plates} source plate(s) and {num_destination_plates} destination plate(s)")
   
    # Step 1: Add water to each destination well
    protocol.comment("Adding water to destination wells")
    
    p20_single.pick_up_tip()
    
    for row in well_data:
        # Access by column name instead of index
        destination_plate_number = row['destination_plate']
        destination_well = row['destination_well']
        water_volume_full = float(row['water_volume'])
        
        # Check if the destination plate number is within the user-specified range
        if int(destination_plate_number) > num_destination_plates:
            protocol.comment(f"Skipping row - destination plate {destination_plate_number} not loaded")
            continue
        
        destination_plate = destination_plates.get(destination_plate_number)
        
        if destination_plate is None:
            protocol.comment(f"Warning: Destination plate {destination_plate_number} not found")
            continue
        
        # Transfer water in 20 µL increments if needed
        if water_volume_full <= 20:
            p20_single.aspirate(water_volume_full, water_well) 
            p20_single.dispense(water_volume_full, destination_plate[destination_well])
        else:
            count_transfers = int(water_volume_full // 20)
            final_transfer = water_volume_full % 20
            
            for _ in range(count_transfers):
                p20_single.aspirate(20, water_well)
                p20_single.dispense(20, destination_plate[destination_well])
            
            if final_transfer > 0:
                p20_single.aspirate(final_transfer, water_well)
                p20_single.dispense(final_transfer, destination_plate[destination_well])
   
    p20_single.drop_tip()

    # Step 2: Add samples to destination wells
    protocol.comment("Adding samples to destination wells")
    
    for row in well_data:
        # Access by column name instead of index
        source_plate_number = row['source_plate']
        source_well = row['source_well']
        destination_plate_number = row['destination_plate']
        destination_well = row['destination_well']
        sample_volume = float(row['sample_volume'])
        
        # Check if plates are within user-specified range
        if int(source_plate_number) > num_source_plates:
            protocol.comment(f"Skipping row - source plate {source_plate_number} not loaded")
            continue
        
        if int(destination_plate_number) > num_destination_plates:
            protocol.comment(f"Skipping row - destination plate {destination_plate_number} not loaded")
            continue
        
        source_plate = source_plates.get(source_plate_number)
        destination_plate = destination_plates.get(destination_plate_number)
        
        if source_plate is None or destination_plate is None:
            protocol.comment(f"Warning: Plate not found for row {row}")
            continue
        
        p20_single.pick_up_tip()
        
        # Mix source sample (5-10 times is typical for DNA samples)
        p20_single.mix(10, 15, source_plate[source_well])
        
        # Transfer sample and mix
        # CHANGE ALL ASPIRATE/DISPENSE TO THESE TRANSFERS
        # Apparently automatically calculates if exceeds pipette volume
        p20_single.transfer(
            sample_volume,
            source_plate[source_well],
            destination_plate,
            mix_after=(5, 10),
            new_tip='always',
            rate=0.3,  # Slow rate for precision
            touch_tip=True,  # Remove droplets
            blow_out=True,          # Blow out remaining liquid
            blowout_location='destination well',
            air_gap=1  # 1 uL gap to prevent dripping
        )

        p20_single.aspirate(sample_volume, source_plate[source_well])
        p20_single.dispense(sample_volume, destination_plate[destination_well])
        
        # Mix sample with water (10 times for thorough mixing of dilution)
        p20_single.mix(10, 15, destination_plate[destination_well])
        
        p20_single.drop_tip()

    protocol.comment("Protocol complete! All steps finished successfully.")
