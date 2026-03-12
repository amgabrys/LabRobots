# 1 protocol that just pools to new plate (to use in big cleaning protocol)
# 1 protocol that does the above and dilutions (where could use just one source plate)
# Remember to add pipette mixes!
# Figure out how to define sample volume at the beginning
# Specify that names of plates must be standardized in document (1,2,3)

from opentrons import protocol_api # Does this get changed?

metadata = {
    'protocolName': 'Plate Combiner',
    'author': 'Ava Gabrys',
    'description': 'Combine multiple plates into one plate, for downstream use in cleaning',
    'source': 'Uhhhh',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="plate_combine_data",
        display_name="Plate Combine CSV",
        description="CSV file with 3 columns: source_plate, source_well, destination_well"
    )
    parameters.add_float(
        display_name="Sample Volume",
        variable_name="sample_volume_full",
        description="Volume in µL to transfer from each source well",
        default=50,
        minimum=5,
        maximum=50
    )

def run(protocol: protocol_api.ProtocolContext):
    # Parse CSV data
    csv_data = protocol.params.plate_combine_data.parse_as_csv()
    
    # Remove header row and process data
    well_data = csv_data[1:]  # Skip header row
    
    # Load labware - streamlined setup
    tiprack_1 = protocol.load_labware('opentrons_96_tiprack_20ul', '1')
    tiprack_2 = protocol.load_labware('opentrons_96_tiprack_20ul', '2')
    source_plate1 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '3')
    source_plate2 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '4')
    source_plate3 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '5')
    source_plate4 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '6')
    source_plate5 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '7')
    destination_plate1 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '8')
    destination_plate2 = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', '9')

    # Load single P20 pipette with both tip racks
    p20_single = protocol.load_instrument('p20_single_gen2', 'right', tip_racks=[tiprack_1, tiprack_2])
    
    # Set slower flow rates for precision with small volumes
    p20_single.flow_rate.aspirate = 3.78
    p20_single.flow_rate.dispense = 3.78

    # Define source plates
    source_plates = {
        "1": source_plate1,
        "2": source_plate2,
        "3": source_plate3,
        "4": source_plate4,
        "5": source_plate5
}
    # Define destination plates
    destination_plates = {
        "1": destination_plate1,
        "2": destination_plate2
}

    # Step 2: Transfer samples individually with mixing (uses 96 tips)
    protocol.comment("Transferring samples with mixing...")
    
    for row in well_data:
        sample_volume_full = row["sample_volume"]
        source_well = row["source_well"]
        destination_well = row["destination_well"]
        destination_plate_number = row["destination_plate"]
        destination_plate = destination_plates.get(destination_plate_number)
        source_plate_number = row["source_plate"]
        source_plate = source_plates.get(source_plate_number)

         # Calculate sample volumes based on input. If it exceeds 20 ul, need to transfer multiple times
        sample_volume_full = protocol.params['sample_volume_full']
        count_transfers = int(sample_volume_full // 20)
        final_transfer = sample_volume_full % 20 # This finds the remainder
        mix_volume = min(sample_volume_full * 0.8, 20)  # Mix 80% of sample at a time, but cap mix volume at 20 µL max

        # Transfer sample
        p20_single.pick_up_tip()
        
        # Change to a proportion of total volume for how much to mix
        # Mix source sample. 
        p20_single.mix(3, mix_volume, source_plate[source_well]) # Mix 3 times, 18 ul
        
        # Take and transfer a full 20 ul at a time for as many times as needed
        for _ in range(int(count_transfers)):
            # Aspirate sample slowly
            p20_single.aspirate(20, source_plate[source_well], rate=0.5)

            # Dispense sample slowly
            p20_single.dispense(20, destination_plate[destination_well], rate=0.5)
        
        # Transfer whatever remains (volume ≤ 20 ul)
        if final_transfer > 0:
            # Aspirate sample slowly
            p20_single.aspirate(final_transfer, source_plate[source_well], rate=0.5)
            # Dispense sample slowly
            p20_single.dispense(final_transfer, destination_plate[destination_well], rate=0.5)
            
        p20_single.drop_tip()
    
    protocol.comment("Plate combining protocol complete!")
    # Adjust
    protocol.comment(f"Total tips used: {len([row for row in well_data if float(row[2]) > 0])}")
