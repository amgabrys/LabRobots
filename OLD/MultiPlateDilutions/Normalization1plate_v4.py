# 1 protocol that just pools to new plate (to use in big cleaning protocol)
# 1 protocol that does the above and dilutions (where could use just one source plate)
# Remember to add pipette mixes!
# Figure out how to define sample volume at the beginning

from opentrons import protocol_api # Does this get changed?

metadata = {
    'protocolName': 'Plate Combiner',
    'author': 'Ava Gabrys',
    'description': 'Combine multiple plates into one plate, for downstream use in cleaning',
    'source': 'Uhhhh'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="plate_combine_data",
        display_name="Plate Combine CSV",
        description="CSV file with 3 columns: source_plate, source_well, destination_well"
    )
def run(protocol: protocol_api.ProtocolContext):
    # Parse CSV data
    csv_data = protocol.params.normalization_data.parse_as_csv()
    
    # Remove header row and process data
    well_data = csv_data[1:]  # Skip header row
    
    # Load labware - streamlined setup
    tiprack_1 = protocol.load_labware('opentrons_96_tiprack_20ul', 1)
    tiprack_2 = protocol.load_labware('opentrons_96_tiprack_20ul', 2)
    source_plate1 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 3)
    source_plate2 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 4)
    source_plate3 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 5)
    source_plate4 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 6)
    source_plate5 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 7)
    destination_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 8)
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 9)
    
    # Load single P20 pipette with both tip racks
    p20_single = protocol.load_instrument('p20_single_gen2', 'right', tip_racks=[tiprack_1, tiprack_2])
    
    # Set slower flow rates for precision with small volumes
    p20_single.flow_rate.aspirate = 3.78
    p20_single.flow_rate.dispense = 3.78

    # Step 1: Collect all water transfer data
    protocol.comment("Preparing transfers...")
    
    for row in well_data:
        source_well = row["source_well"]
        source_plate = row["source_plate"]
        destination_well = row["destination_well"]

    # Step 2: Transfer samples individually with mixing (uses 96 tips)
    protocol.comment("Transferring samples with mixing...")
    
    for row in well_data:
        source_well = row["source_well"]
        source_plate = row["source_plate"]
        destination_well = row["destination_well"]
        
        # Transfer sample
        p20_single.pick_up_tip()
        
        # Change to multi-mix
        # Mix source sample
        p20_single.mix(3, min(sample_volume * 0.8, 20), source_plate[source_well])
            
        # Aspirate sample slowly
        p20_single.aspirate(sample_volume, source_plate[source_well], rate=0.5)

        p200.transfer(100, plate.wells('A1'), plate.wells('B1'))
            
            # Dispense sample slowly
            # This needs to be from the specific origin plate
            p20_single.dispense(sample_volume, destination_plate[source_well], rate=0.5)
            
            # Mix final solution (use 80% of total volume, max 16µL for P20)
            mix_volume = min(8, 16)  # 80% of 10µL total, but max 16µL for P20
            p20_single.mix(5, mix_volume, destination_plate[source_well])
            
            p20_single.drop_tip()
    
    protocol.comment("Plate combining protocol complete!")
    protocol.comment(f"Total tips used: {1 + len([row for row in well_data if float(row[2]) > 0])}")


    








from opentrons import protocol_api

metadata = {
    'protocolName': 'Streamlined Plate Normalization Protocol',
    'author': 'OpentronsAI',
    'description': 'Normalize samples using minimal hardware: 2 PCR plates, 1 reservoir, 2 tip racks, 1 pipette (97 tips total)',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="normalization_data",
        display_name="Normalization CSV",
        description="CSV file with columns: source_well, water_volume, sample_volume"
    )

def run(protocol: protocol_api.ProtocolContext):
    # Parse CSV data
    csv_data = protocol.params.normalization_data.parse_as_csv()
    
    # Remove header row and process data
    well_data = csv_data[1:]  # Skip header row
    
    # Load labware - streamlined setup
    tiprack_1 = protocol.load_labware('opentrons_96_tiprack_20ul', 1)
    tiprack_2 = protocol.load_labware('opentrons_96_tiprack_20ul', 2)
    source_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 3)
    destination_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 4)
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 5)
    
    # Load single P20 pipette with both tip racks
    p20_single = protocol.load_instrument('p20_single_gen2', 'right', tip_racks=[tiprack_1, tiprack_2])
    
    # Set slower flow rates for precision with small volumes
    p20_single.flow_rate.aspirate = 3.78
    p20_single.flow_rate.dispense = 3.78
    
    # Water source is in first well of reservoir
    water_source = reservoir['A1']
    
    # Prepare lists for batch processing
    water_destinations = []
    water_volumes = []
    
    # Step 1: Collect all water transfer data
    protocol.comment("Preparing water transfers...")
    
    for row in well_data:
        source_well = row[0]
        water_volume = float(row[1])
        sample_volume = float(row[2])
        
        # Validate volumes
        total_volume = water_volume + sample_volume
        if total_volume != 10.0:
            protocol.comment(f"Warning: Total volume for {source_well} is {total_volume} µL, not 10 µL")
        
        # Add to water transfer lists if volume > 0
        if water_volume > 0:
            water_destinations.append(destination_plate[source_well])
            water_volumes.append(water_volume)
    
    # Step 2: Perform batch water transfers (uses 1 tip)
    protocol.comment("Adding water to destination wells...")
    
    if water_destinations:
        p20_single.transfer(
            water_volumes,
            water_source,
            water_destinations,
            new_tip='once'  # Use same tip for all water transfers
        )
    
    # Step 3: Transfer samples individually with mixing (uses 96 tips)
    protocol.comment("Transferring samples with mixing...")
    
    for row in well_data:
        source_well = row[0]
        water_volume = float(row[1])
        sample_volume = float(row[2])
        
        # Transfer sample if volume > 0
        if sample_volume > 0:
            p20_single.pick_up_tip()
            
            # Mix source sample
            p20_single.mix(3, min(sample_volume * 0.8, 20), source_plate[source_well])
            
            # Aspirate sample slowly
            p20_single.aspirate(sample_volume, source_plate[source_well], rate=0.5)
            
            # Dispense sample slowly
            p20_single.dispense(sample_volume, destination_plate[source_well], rate=0.5)
            
            # Mix final solution (use 80% of total volume, max 16µL for P20)
            mix_volume = min(8, 16)  # 80% of 10µL total, but max 16µL for P20
            p20_single.mix(5, mix_volume, destination_plate[source_well])
            
            p20_single.drop_tip()
    
    protocol.comment("Normalization protocol complete!")
    protocol.comment(f"Total tips used: {1 + len([row for row in well_data if float(row[2]) > 0])}")