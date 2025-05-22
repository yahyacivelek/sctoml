"""
Converts sctoml (State Chart TOML) files to Quantum Leaps QM model XML format (qmxml).

This script takes a TOML file describing a state machine and outputs an XML file
compatible with the QM modeling tool. It maps sctoml structures to their
corresponding QMXML elements, including classes, statecharts, states (nested),
entry/exit actions, initial transitions, event-triggered transitions, choices,
and guards. Default placeholders are used for diagrammatic attributes not
specified in sctoml.
"""
import toml
import argparse
import xml.etree.ElementTree as ET

def process_toml_states(parent_xml_element, current_level_states_dict):
    """
    Recursively processes a dictionary of states defined in TOML and appends
    the corresponding XML state structures to the parent_xml_element.

    This function handles the hierarchical nature of states. For each state, it:
    1. Creates a <state> XML element.
    2. Processes 'enter' and 'exit' actions, mapping them to <entry> and <exit> XML elements.
       If the action code is an empty string, it's represented as brief="" and empty text.
       If the action is not defined in TOML, no element is created.
    3. Adds a default <state_glyph> for diagrammatic representation in QM.
    4. Processes a nested 'initial' transition if defined for a composite state.
       The target is made relative (e.g., "../SubstateName"). An empty target implies
       an initial transition to the composite state itself (though typically should target a substate).
       Includes a default <initial_glyph> and <action>.
    5. Processes 'events' (transitions):
        - Each event maps to a <tran> XML element. The 'sig' field becomes the 'trig' attribute.
          If 'sig' is missing, "EVENT_NAME_MISSING" is used as a placeholder.
        - A default <tran_glyph> and <action> are added.
        - If 'target' is a string, it's a simple transition. Target path is relative.
        - If 'target' is a list, it represents <choice> points:
            - Each item in the 'target' list becomes a <choice> element with a relative target.
            - 'condition' or 'conditions' from TOML map to <guard> elements for these choices.
            - If conditions are fewer than targets, the last choice gets an implicit "ELSE" guard.
            - Each <choice> gets a default <choice_glyph> and <action>.
        - If 'target' is not specified, it's an internal transition (no target attribute on <tran>).
    6. Filters out reserved keys ('enter', 'exit', 'events', 'initial') and recursively calls
       itself for any remaining dictionary items, treating them as nested states.
    """
    reserved_keys = ["enter", "exit", "events", "initial"] # Keys defining state properties, not nested states

    for state_name, state_definition_dict in current_level_states_dict.items():
        if state_name in reserved_keys:
            continue # Skip properties of the parent state, process them as part of state_definition_dict

        state_elem = ET.SubElement(parent_xml_element, "state", attrib={"name": state_name})

        # Entry Action
        entry_action_code = state_definition_dict.get("enter")
        if entry_action_code is not None: # Only add if key exists (even if empty string)
            entry_elem = ET.SubElement(state_elem, "entry", attrib={"brief": entry_action_code if entry_action_code else ""})
            entry_elem.text = entry_action_code if entry_action_code else ""
        
        # Exit Action
        exit_action_code = state_definition_dict.get("exit")
        if exit_action_code is not None: # Only add if key exists
            exit_elem = ET.SubElement(state_elem, "exit", attrib={"brief": exit_action_code if exit_action_code else ""})
            exit_elem.text = exit_action_code if exit_action_code else ""

        # Default State Glyph (visual placeholder)
        ET.SubElement(state_elem, "state_glyph", attrib={"color": "0", "node": "0,0,0,0"})

        # Nested Initial State (for composite states pointing to a substate)
        nested_initial_target = state_definition_dict.get("initial")
        if nested_initial_target is not None and isinstance(nested_initial_target, str):
            # Target path is relative to the current state's parent (the statechart or a superstate)
            target_val = f"../{nested_initial_target}" if nested_initial_target else ""
            nested_initial_elem = ET.SubElement(state_elem, "initial", attrib={"target": target_val})
            nested_initial_glyph = ET.SubElement(nested_initial_elem, "initial_glyph", attrib={"color": "0", "conn": "0,0,0,0"})
            ET.SubElement(nested_initial_glyph, "action") # Empty action for initial transition

        # Process Events (Transitions)
        events_list = state_definition_dict.get("events", [])
        for event_data in events_list:
            sig = event_data.get("sig")
            target = event_data.get("target")
            # 'condition' for single guard, 'conditions' for list of guards for choices
            condition_val = event_data.get("condition", event_data.get("conditions"))

            # Construct trigger string: comma-separated if list, else direct. Default if missing.
            trigger_str = ",".join(sig) if isinstance(sig, list) else sig
            final_trigger_str = trigger_str if trigger_str else "EVENT_NAME_MISSING"

            tran_elem = ET.SubElement(state_elem, "tran", attrib={"trig": final_trigger_str})
            
            # Default transition glyph and action (visual placeholder)
            tran_glyph = ET.SubElement(tran_elem, "tran_glyph", attrib={"color": "0", "conn": "0,0,0,0"})
            ET.SubElement(tran_glyph, "action") 

            if isinstance(target, str): # Simple transition
                # Target path is relative
                tran_elem.set("target", f"../{target}" if target else "")
            elif isinstance(target, list): # Choices (conditional transitions)
                actual_conditions = []
                if isinstance(condition_val, list):
                    actual_conditions = condition_val
                elif isinstance(condition_val, str): # Single condition can apply to first choice
                    actual_conditions = [condition_val]

                for i in range(len(target)):
                    current_choice_target_str = target[i]
                    choice_attrib = {}
                    if current_choice_target_str: # Target can be empty string (e.g. stay in state)
                        # Target path is relative
                        choice_attrib["target"] = f"../{current_choice_target_str}"
                    
                    choice_elem = ET.SubElement(tran_elem, "choice", attrib=choice_attrib)

                    guard_elem = ET.SubElement(choice_elem, "guard")
                    guard_text = ""
                    if i < len(actual_conditions):
                        guard_text = actual_conditions[i] if actual_conditions[i] is not None else "" 
                    elif i == len(target) - 1 and i >= len(actual_conditions): # Implicit ELSE for the last choice
                        guard_text = "ELSE"
                    
                    guard_elem.text = guard_text
                    guard_elem.set("brief", guard_text) # 'brief' attribute mirrors the text content for guard

                    # Default choice glyph and action (visual placeholder)
                    choice_glyph = ET.SubElement(choice_elem, "choice_glyph", attrib={"color": "0", "conn": "0,0,0,0"})
                    ET.SubElement(choice_glyph, "action") 
            # If target is None, it's an internal transition; <tran> element has no 'target' attribute.
            
        # Recursive call for nested states:
        # Filter state_definition_dict to get only items that are dictionaries (potential substates)
        # and are not among the reserved keys already processed.
        sub_states_dict = {
            k: v for k, v in state_definition_dict.items() 
            if k not in reserved_keys and isinstance(v, dict)
        }
        if sub_states_dict:
            process_toml_states(state_elem, sub_states_dict)

def main():
    # 1. Argument Parsing
    parser = argparse.ArgumentParser(description="Convert sctoml (State Chart TOML) files to QMXML.")
    parser.add_argument("input_toml_file", help="Path to the input TOML file.")
    parser.add_argument("output_xml_file", help="Path to the output QMXML file.")
    args = parser.parse_args()

    print(f"Input TOML file: {args.input_toml_file}")
    print(f"Output QMXML file: {args.output_xml_file}")

    try:
        # 2. TOML Loading
        with open(args.input_toml_file, 'r') as f:
            toml_data = toml.load(f)
        
        # 3. XML Generation - Setup basic QMXML structure
        root_model = ET.Element("model", attrib={"links": "?", "version": "1.0.0"}) # QM model root
        ET.SubElement(root_model, "framework", attrib={"name": "QP"}) # Framework specification
        # Default package for all classes
        package_elem = ET.SubElement(root_model, "package", attrib={"name": "DefaultPackage", "stereotype": "0x00"})

        # Process each 'object' (class) defined in TOML
        objects_data = toml_data.get('object', [])
        for object_data in objects_data:
            obj_name = object_data.get('name', 'UnnamedClass') # Default class name
            class_elem = ET.SubElement(package_elem, "class", attrib={"name": obj_name})
            statechart_elem = ET.SubElement(class_elem, "statechart", attrib={"properties": "0x00"}) # Basic statechart properties
            
            # Add state_diagram element (visual placeholder)
            ET.SubElement(statechart_elem, "state_diagram", attrib={"size": "800,600"})

            # Top-level initial transition for the statechart
            initial_state_name_top = object_data.get('initial')
            if initial_state_name_top:
                # Target path is relative to statechart's parent (the class)
                initial_tran_elem = ET.SubElement(statechart_elem, "initial", attrib={"target": f"../{initial_state_name_top}"})
                initial_glyph_elem = ET.SubElement(initial_tran_elem, "initial_glyph", attrib={"color": "0", "conn": "0,0,0,0"})
                ET.SubElement(initial_glyph_elem, "action") # Empty action for initial transition

            # Process all states defined under this object (class)
            top_level_states_data = object_data.get('states', {})
            process_toml_states(statechart_elem, top_level_states_data)

        tree = ET.ElementTree(root_model)

        # 4. Writing Output XML
        # Attempt to pretty-print the XML if ET.indent is available (Python 3.9+)
        try:
            ET.indent(tree, space="\t", level=0)
        except AttributeError:
            # ET.indent not available, output will not be pretty-printed
            pass 
            
        tree.write(args.output_xml_file, encoding="UTF-8", xml_declaration=True)
        print(f"Successfully converted '{args.input_toml_file}' to '{args.output_xml_file}'")

    except FileNotFoundError:
        print(f"Error: Input TOML file not found: {args.input_toml_file}")
    except toml.TomlDecodeError:
        print(f"Error: Could not decode TOML file: {args.input_toml_file}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
