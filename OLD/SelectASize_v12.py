from opentrons import protocol_api
from opentrons import types

metadata = {
    'protocolName': 'Automated Supplemental Protocol - Basic Aliquoting with Magnetic Bead Cleanup V2',
    'author': 'OpentronsAI',
    'description': 'A protocol for basic aliquoting and magnetic bead cleanup on the Opentrons Flex with P1000 for bead mixing.',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'Flex',
    'apiLevel': '2.19'
}

def add_parameters(parameters):
    parameters.add_float(
        display_name="MagBead Incubation (min)",
        variable_name="magbead_incubation_time",
        description="The time in minutes for the magnetic bead incubation step.",
        default=5.0,
        minimum=1.0,
        maximum=30.0
    )
    parameters.add_float(
        display_name="Bead Mixing Volume (µL)",
        variable_name="bead_mixing_volume",
        description="Volume in µL to use for magnetic bead mixing operations.",
        default=200.0,
        minimum=50.0,
        maximum=800.0
    )
    parameters.add_bool(
        display_name="Dry Run",
        variable_name="DryRun",
        description="A dry run will skip all delays and speed up movements.",
        default=False
    )

def run(protocol: protocol_api.ProtocolContext):
    
    # PARAMETERS
    magbead_incubation_time = protocol.params.magbead_incubation_time
    bead_mixing_volume = protocol.params.bead_mixing_volume
    DryRun = protocol.params.DryRun

    # PIPETTES - Reversed configuration
    pip50 = protocol.load_instrument(
        instrument_name="flex_8channel_50",
        mount="left")
    
    pip1000 = protocol.load_instrument(
        instrument_name="flex_8channel_1000", 
        mount="right")   # P1000 now on left for bead mixing

    # FLOW RATES - Optimized for small volumes (P50) and bead mixing (P1000)
    pip50.flow_rate.aspirate = 10  # Very slow for small volumes
    pip50.flow_rate.dispense = 20  # Controlled dispensing
    pip50.flow_rate.blow_out = 50  # Moderate blow out
    
    pip1000.flow_rate.aspirate = 50   # Standard for bead mixing
    pip1000.flow_rate.dispense = 150  # Standard for bead mixing
    pip1000.flow_rate.blow_out = 300  # Standard blow out

    # FIXTURES - Updated waste bin location
    trash = protocol.load_trash_bin("D3")
    
    # MODULES - Updated locations per your specifications
    temp_module = protocol.load_module('temperature module gen2', 'A3')
    temp_adapter = temp_module.load_adapter('opentrons_96_well_aluminum_block')
    mag_block = protocol.load_module('magneticBlockV1', 'C1') 
    heater_shaker = protocol.load_module('heaterShakerModuleV1', 'D1')
    
    # LABWARE
    # Tip racks - Updated for both pipettes
    water_tips_50 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'A1')
    wash_tips_50 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'B1')
    magbead_tips_1000 = protocol.load_labware('opentrons_flex_96_tiprack_1000ul', 'A2')
    mixing_tips_1000 = protocol.load_labware('opentrons_flex_96_tiprack_1000ul', 'B2')
    
    # Plates and reservoirs - Consolidated into single 12-well reservoir
    sample_plate = temp_adapter.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt')
    final_elution_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 'C2')
    reagent_reservoir = protocol.load_labware('nest_12_reservoir_15ml', 'D2')  # Single consolidated reservoir
    waste_reservoir = protocol.load_labware('nest_12_reservoir_15ml', 'C3')  # Waste reservoir
    
    # LIQUIDS - Updated volumes and locations
    dnase_free_water = reagent_reservoir.wells()[0]  # Well 1: 3 mL of Water (reduced from 7 mL)
    dna_wash_buffer = reagent_reservoir.wells()[2]   # Well 3: 6 mL DNA Wash Buffer  
    water_magbead_mix = reagent_reservoir.wells()[11]  # Well 12: Combined water and magbeads
    waste = waste_reservoir.wells()[0]
    
    # Define liquids for loading template
    water_liquid = protocol.define_liquid(
        name="DNase Free Water",
        description="DNase free water for dilution and elution",
        display_color="#0000FF"
    )
    
    wash_buffer_liquid = protocol.define_liquid(
        name="DNA Wash Buffer", 
        description="DNA wash buffer for cleanup",
        display_color="#00FF00"
    )
    
    water_magbead_liquid = protocol.define_liquid(
        name="Water + Magnetic Bead Mix",
        description="Combined water and magnetic beads in binding buffer",
        display_color="#8B4513"
    )
    
    # Load liquids according to updated template
    dnase_free_water.load_liquid(liquid=water_liquid, volume=3000)      # 3 mL in well 1 (reduced)
    dna_wash_buffer.load_liquid(liquid=wash_buffer_liquid, volume=6000) # 6 mL in well 3  
    water_magbead_mix.load_liquid(liquid=water_magbead_liquid, volume=3347.5)  # Combined mix in well 12
    
    # Wells to be used - 8-channel processes columns
    sample_columns = sample_plate.columns()
    elution_columns = final_elution_plate.columns()
    
    # FUNCTIONS
    def drop_tip_50():
        if DryRun:
            pip50.return_tip()
        else:
            pip50.drop_tip(trash)
            
    def drop_tip_1000():
        if DryRun:
            pip1000.return_tip()
        else:
            pip1000.drop_tip(trash)

    def bead_mixing(well, pip, mvol, reps=8):
        """Enhanced mixing function specifically for magnetic beads with complex movement patterns"""
        center = well.top().move(types.Point(x=0,y=0,z=5))
        aspbot = well.bottom().move(types.Point(x=0,y=2,z=1))
        asptop = well.bottom().move(types.Point(x=0,y=-2,z=2))
        disbot = well.bottom().move(types.Point(x=0,y=2,z=3))
        distop = well.top().move(types.Point(x=0,y=1,z=-5))

        if mvol > 1000:
            mvol = 1000

        vol = mvol * .8

        pip.flow_rate.aspirate = 500
        pip.flow_rate.dispense = 500

        pip.move_to(center)
        for _ in range(reps):
            pip.aspirate(vol,aspbot)
            pip.dispense(vol,distop)
            pip.aspirate(vol,asptop)
            pip.dispense(vol,disbot)
            if _ == reps-1:
                pip.flow_rate.aspirate = 150
                pip.flow_rate.dispense = 100
                pip.aspirate(vol,aspbot)
                pip.dispense(vol,distop)

        pip.flow_rate.aspirate = 50   # Reset to standard for P1000
        pip.flow_rate.dispense = 150

    def mixing(well, pip, mvol, reps=8):
        """Standard mixing function for general liquid mixing"""
        center = well.top(5)
        asp = well.bottom(1)
        disp = well.top(-8)

        if mvol > 1000:
            mvol = 1000

        vol = mvol * .8

        pip.flow_rate.aspirate = 500
        pip.flow_rate.dispense = 500

        pip.move_to(center)
        for _ in range(reps):
            pip.aspirate(vol,asp)
            pip.dispense(vol,disp)
            pip.aspirate(vol,asp)
            pip.dispense(vol,disp)
            if _ == reps-1:
                pip.flow_rate.aspirate = 150
                pip.flow_rate.dispense = 100
                pip.aspirate(vol,asp)
                pip.dispense(vol,disp)

        # Reset flow rates based on pipette type
        if pip == pip50:
            pip.flow_rate.aspirate = 10
            pip.flow_rate.dispense = 20
        else:  # pip1000
            pip.flow_rate.aspirate = 50
            pip.flow_rate.dispense = 150

    # PROTOCOL STEPS
    protocol.comment('------STARTING BASIC ALIQUOTING & CLEANUP PROTOCOL------')
    protocol.comment('LIQUID LOADING TEMPLATE:')
    protocol.comment('- Well 1: 3 mL DNase Free Water')
    protocol.comment('- Well 3: 6 mL DNA Wash Buffer') 
    protocol.comment('- Well 12: 3.35 mL Water + Magnetic Bead Mix (1287.5 uL water + 2060 uL magbeads)')
    protocol.comment(f'- Bead mixing volume set to: {bead_mixing_volume} µL')
    
    # BATCH PROCESSING - Combined water and magbead addition using P50
    protocol.comment('BATCH STEP 1: Adding 26 uL of water + magbead mix to all samples')
    water_magbead_mixed = False  # Track if mix has been mixed from reservoir
    
    for col_idx in range(12):  # Process all 12 columns
        current_column = sample_columns[col_idx]
        
        # Use P1000 for mixing magbeads in reservoir
        pip1000.pick_up_tip(magbead_tips_1000.columns()[col_idx][0])
        
        # Mix water + magbead mixture in reservoir - Use bead_mixing with parameter volume
        if not water_magbead_mixed:
            bead_mixing(water_magbead_mix, pip1000, bead_mixing_volume, 15)  # First time: 15 reps
            water_magbead_mixed = True
        else:
            bead_mixing(water_magbead_mix, pip1000, bead_mixing_volume, 10)  # Subsequent: 10 reps
        
        pip1000.return_tip()
        
        # Use P50 for precise small volume transfer
        pip50.pick_up_tip(water_tips_50.columns()[col_idx][0])
        pip50.aspirate(26, water_magbead_mix.bottom(0.3))
        pip50.dispense(26, current_column[0].bottom(0.3))
        pip50.return_tip()
        
        # Use P1000 for thorough bead mixing in sample
        pip1000.pick_up_tip(mixing_tips_1000.columns()[col_idx][0])
        bead_mixing(current_column[0], pip1000, bead_mixing_volume, 20)
        pip1000.return_tip()
    
    # Step 3: Incubate at Room Temperature
    protocol.comment('Step 3: Incubating at room temperature.')
    if not DryRun:
        protocol.delay(minutes=5, msg="Incubating with magnetic beads at room temperature.")
    else:
        protocol.delay(seconds=30, msg="Dry run: Incubation with magnetic beads.")

    # Step 4: Move samples to magnetic rack (C1)
    protocol.comment('Step 4: Moving samples to magnetic rack.')
    protocol.move_labware(
        labware=sample_plate, 
        new_location=mag_block, 
        use_gripper=True)
    
    # Step 5: Incubate for magnetic separation
    protocol.comment(f'Step 5: Incubating for {magbead_incubation_time} minutes for magnetic separation.')
    if not DryRun:
        protocol.delay(minutes=magbead_incubation_time, msg="Magnetic separation.")
    else:
        protocol.delay(seconds=30, msg="Dry run: Magnetic separation.")
    
    # BATCH PROCESSING - Remove all supernatants using P50
    protocol.comment('BATCH STEP 6: Removing supernatant from all samples')
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        
        pip50.pick_up_tip(water_tips_50.columns()[col_idx][0])
        pip50.aspirate(35, current_column[0].bottom(0.3), rate=0.1)
        pip50.dispense(35, waste)  # Dispose to waste reservoir in C3
        drop_tip_50()

    # BATCH PROCESSING - Add wash buffer to all samples using P50
    protocol.comment('BATCH STEP 7: Adding wash buffer to all samples')
    wash_buffer_mixed = False  # Track if wash buffer has been mixed
    
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        
        # Use P1000 for mixing wash buffer in reservoir
        if not wash_buffer_mixed:
            pip1000.pick_up_tip(mixing_tips_1000.columns()[col_idx][0])
            mixing(dna_wash_buffer, pip1000, bead_mixing_volume, 5)  # Mix with parameter volume
            pip1000.return_tip()
            wash_buffer_mixed = True
        
        # Use P50 for precise transfer
        pip50.pick_up_tip(wash_tips_50.columns()[col_idx][0])
        pip50.aspirate(50, dna_wash_buffer.bottom(0.3))
        pip50.dispense(50, current_column[0].bottom(0.5))
        pip50.blow_out(current_column[0].top(-2))
        pip50.return_tip()
    
    # BATCH PROCESSING - Remove all wash supernatants using P50
    protocol.comment('BATCH STEP 9: Removing wash from all samples')
    if not DryRun:
        protocol.pause("Ensure all residual buffer is removed. Press continue to proceed.")
    
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        
        pip50.pick_up_tip(wash_tips_50.columns()[col_idx][0])
        pip50.aspirate(50, current_column[0].bottom(0.3), rate=0.10)
        pip50.dispense(50, waste)  # Dispose to waste reservoir in C3
        drop_tip_50()
        
    # BATCH PROCESSING - Add elution water to all samples using P50
    protocol.comment('BATCH STEP 10: Adding elution water to all samples')
    water_mixed_for_elution = False  # Track if water has been mixed for elution
    
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        
        # Use P1000 for mixing water in reservoir
        if not water_mixed_for_elution:
            pip1000.pick_up_tip(mixing_tips_1000.columns()[col_idx][0])
            mixing(dnase_free_water, pip1000, bead_mixing_volume, 5)  # Mix with parameter volume
            pip1000.return_tip()
            water_mixed_for_elution = True
        
        # Use P50 for precise transfer
        pip50.pick_up_tip(water_tips_50.columns()[col_idx][0])
        pip50.aspirate(20, dnase_free_water.bottom(0.2))
        pip50.dispense(20, current_column[0].bottom(0.2))
        pip50.return_tip()

    # Step 11: Remove from magnetic rack and mix vigorously
    protocol.comment('Step 11: Removing plate from magnet and mixing vigorously.')
    protocol.move_labware(
        labware=sample_plate, 
        new_location=temp_adapter, 
        use_gripper=True)
    
    # BATCH PROCESSING - Mix all samples for elution using P1000
    protocol.comment('BATCH STEP 11: Mixing all samples for elution')
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        pip1000.pick_up_tip(mixing_tips_1000.columns()[col_idx][0])
        # Use bead_mixing for elution since we're still working with magnetic beads
        bead_mixing(current_column[0], pip1000, bead_mixing_volume, 20)
        pip1000.return_tip()

    # Step 12: Incubate at room temperature for 5 minutes
    protocol.comment('Step 12: Elution incubation for 5 minutes at room temperature.')
    if not DryRun:
        protocol.delay(minutes=5, msg="Elution incubation.")
    else:
        protocol.delay(seconds=30, msg="Dry run: Elution incubation.")

    # Step 13: Place back on magnetic rack for final separation
    protocol.comment('Step 13: Placing samples back on magnetic rack.')
    protocol.move_labware(
        labware=sample_plate, 
        new_location=mag_block, 
        use_gripper=True)
    
    # Step 14: Final magnetic separation and transfer eluted DNA
    protocol.comment('Step 14: Final magnetic separation and transferring eluted DNA.')
    if not DryRun:
        protocol.delay(minutes=magbead_incubation_time, msg="Final magnetic separation.")
    else:
        protocol.delay(seconds=30, msg="Dry run: Final magnetic separation.")

    # BATCH PROCESSING - Transfer all eluted DNA using P50
    protocol.comment('BATCH STEP 14: Transferring eluted DNA from all samples')
    for col_idx in range(12):
        current_column = sample_columns[col_idx]
        elution_column = elution_columns[col_idx]
        
        pip50.pick_up_tip(water_tips_50.columns()[col_idx][0])
        pip50.aspirate(18, current_column[0].bottom(0.2), rate=0.1)
        pip50.dispense(18, elution_column[0].bottom(0.5))
        pip50.blow_out(elution_column[0].top(-2))
        drop_tip_50()

    protocol.comment('------PROTOCOL COMPLETE------')
    protocol.comment('LIQUID LOADING TEMPLATE USED:')
    protocol.comment('- Well 1: 3 mL DNase Free Water')
    protocol.comment('- Well 3: 6 mL DNA Wash Buffer') 
    protocol.comment('- Well 12: 3.35 mL Water + Magnetic Bead Mix (1287.5 uL water + 2060 uL magbeads)')
    protocol.comment(f'- Bead mixing volume used: {bead_mixing_volume} µL')