from opentrons import protocol_api

metadata = {
    'protocolName': 'ZR-96 DNA Clean & Concentrator-5 Protocol',
    'author': 'OpentronsAI',
    'description': 'DNA binding buffer transfer, wash buffer addition, and water elution with centrifuge pauses',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_int(
        variable_name="sample_volume",
        display_name="Sample Volume",
        description="Volume of sample in each well (µL)",
        default=50,
        minimum=0,
        maximum=100
    )
    
    parameters.add_int(
        variable_name="water_volume",
        display_name="Water Volume",
        description="Volume of DNase-free water to add to each well (µL)",
        default=15,
        minimum=10,
        maximum=20
    )

def run(protocol: protocol_api.ProtocolContext):
    # Access runtime parameters
    sample_vol = protocol.params.sample_volume
    water_vol = protocol.params.water_volume
    
    # Calculate binding buffer volume based on sample volume
    if sample_vol <= 50:
        binding_buffer_vol = 100
    else:
        binding_buffer_vol = 2 * sample_vol
    
    # Load labware - optimized to use single reservoir
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 5, 'Reagent Reservoir')
    pcr_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 2, 'PCR Plate with Samples')
    deep_well_plate = protocol.load_labware('nest_96_wellplate_2ml_deep', 4, 'Deep Well Plate')
    
    # Load tip racks - increased number for additional tip changes
    tips_200_1 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 3)
    tips_200_2 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 6)
    tips_200_3 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 9)  # Additional tip rack
    tips_20 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 8)
    
    # Load pipettes
    p300_multi = protocol.load_instrument('p300_multi_gen2', 'left', tip_racks=[tips_200_1, tips_200_2, tips_200_3])
    p20_multi = protocol.load_instrument('p20_multi_gen2', 'right', tip_racks=[tips_20])
    
    # Define reagent locations in single reservoir
    # Wells A1-A2: DNA Binding Buffer (5000 µL each)
    # Wells A3-A11: DNA Wash Buffer (distributed across wells) # No more like this
    # Well A12: DNase-free water (1800 µL)
    binding_buffer_wells = [reservoir['A1'], reservoir['A2']]
    water_well = reservoir['A12']
    wash_buffer_wells = [reservoir['A3'], reservoir['A4'], reservoir['A5'], reservoir['A6']]

    # Define liquids for plate map
    binding_buffer_liquid = protocol.define_liquid(
        name="DNA Binding Buffer",
        description="DNA Binding Buffer for sample processing",
        display_color="#FF6600"
    )
    
    wash_buffer_liquid = protocol.define_liquid(
        name="DNA Wash Buffer", 
        description="DNA Wash Buffer for cleaning",
        display_color="#0066FF"
    )
    
    water_liquid = protocol.define_liquid(
        name="DNase-free Water",
        description="DNase-free water for elution",
        display_color="#00FFFF"
    )
    
    sample_liquid = protocol.define_liquid(
        name="DNA Sample",
        description=f"DNA samples ({sample_vol} µL each)",
        display_color="#00FF00"
    )
    
    # Load liquids into labware for plate map
    for well in binding_buffer_wells:
        well.load_liquid(liquid=binding_buffer_liquid, volume=5000)
    
    wash_volumes = [15000, 15000, 15000, 15000]
    for well, vol in zip(wash_buffer_wells, wash_volumes):
        well.load_liquid(liquid=wash_buffer_liquid, volume=vol)
    
    water_well.load_liquid(liquid=water_liquid, volume=1800)
    
    for well in pcr_plate.wells():
        well.load_liquid(liquid=sample_liquid, volume=sample_vol)
    
    protocol.comment(f"Starting ZR-96 DNA Clean & Concentrator-5 Protocol")
    protocol.comment(f"Sample volume: {sample_vol} µL")
    protocol.comment(f"Binding buffer volume: {binding_buffer_vol} µL")
    protocol.comment(f"Water volume: {water_vol} µL")
    
    # Step 1: Transfer DNA Binding Buffer and mix samples
    protocol.comment("Step 1: Adding DNA Binding Buffer to samples")
    
    # Transfer binding buffer and mix, then transfer to deep well plate with new tips each time
    for i, column in enumerate(pcr_plate.columns()):
        # Pick up tip for binding buffer addition and mixing
        p300_multi.pick_up_tip()
        
        # Alternate between wells A1 and A2 for binding buffer
        source_well = binding_buffer_wells[i % 2]
        
        # Transfer binding buffer to PCR plate
        p300_multi.aspirate(binding_buffer_vol, source_well)
        p300_multi.dispense(binding_buffer_vol, column[0])
        
        # Mix 10 times
        p300_multi.mix(10, 150, column[0])
        
        # Drop tip after mixing
        p300_multi.drop_tip()
        
        # Pick up new tip for transfer to deep well plate
        p300_multi.pick_up_tip()
        
        # Transfer mixed solution to deep well plate with settling and blow out
        p300_multi.aspirate(sample_vol + binding_buffer_vol, column[0])
        p300_multi.dispense(sample_vol + binding_buffer_vol, deep_well_plate.columns()[i][0])
        protocol.delay(seconds=1)  # Let solution settle
        p300_multi.blow_out(deep_well_plate.columns()[i][0])
        
        # Drop tip after transfer to deep well plate
        p300_multi.drop_tip()
    
    # Pause for centrifugation
    protocol.pause("Remove the deep well plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 2: First wash buffer addition (300 µL in two 150 µL increments)
    protocol.comment("Step 2: Adding first wash buffer (300 µL total)")
    p300_multi.pick_up_tip()
    
    # First 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)  # Let solution settle
        p300_multi.blow_out(column[0])
    
    # Second 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)  # Let solution settle
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()
    
    # Pause for centrifugation
    protocol.pause("Remove the deep well plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 3: Second wash buffer addition (300 µL in two 150 µL increments)
    protocol.comment("Step 3: Adding second wash buffer (300 µL total)")
    p300_multi.pick_up_tip()
    
    # First 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)  # Let solution settle
        p300_multi.blow_out(column[0])
    
    # Second 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)  # Let solution settle
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()
    
    # Pause for centrifugation
    protocol.pause("Remove the deep well plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 4: Add DNase-free water
    protocol.comment(f"Step 4: Adding {water_vol} µL of DNase-free water to each well")
    
    # Use P20 multi-channel for water addition
    p20_multi.transfer(
        water_vol,
        water_well,
        [column[0] for column in deep_well_plate.columns()],
        new_tip='once'
    )
    
    protocol.comment("Protocol complete! All steps finished successfully.")
    
    # Display reagent setup information
    protocol.comment("=== REAGENT SETUP GUIDE ===")
    protocol.comment(f"Reservoir Well A1: 5000 µL DNA Binding Buffer")
    protocol.comment(f"Reservoir Well A2: 5000 µL DNA Binding Buffer") 
    protocol.comment(f"Reservoir Wells A3-A6: 15,000 µL DNA Wash Buffer each")
    protocol.comment(f"Reservoir Well A12: 1800 µL DNase-free Water")
    protocol.comment(f"PCR Plate: {sample_vol} µL DNA sample in each well")
