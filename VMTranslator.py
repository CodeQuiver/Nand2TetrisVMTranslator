import os
import re
import sys


# Constants
segments = {
    "local": "LCL",
    "argument": "ARG",
    "this": "THIS",
    "that": "THAT",
    "pointer": {
        0: "THIS",
        1: "THAT",
    },
}

# Command string translations
sub_comms = {
    "dec1save": "@SP\nAM=M-1\nM=D",
    "dec2save": "@SP\nM=M-1\nAM=M-1\nM=D",
    "inc": "@SP\nM=M+1",
    "dec": "@SP\nM=M-1",
    "pop_top_stack_to_D": "@SP\nAM=M-1\nD=M",
    "setup2vals": "@SP\nD=M-1\nA=D-1\nD=M\n@SP\nA=M-1",
    "push_val_in_D_to_stack": "D=M\n@SP\nA=M\nM=D",
}

arith_comms = {
    "add": f"{sub_comms['setup2vals']}\nD=D+M\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
    "sub": f"{sub_comms['setup2vals']}\nD=D-M\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
    "and": f"{sub_comms['setup2vals']}\nD=D&M\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
    "or": f"{sub_comms['setup2vals']}\nD=D|M\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
    "not": f"@SP\nA=M-1\nM=!M",
    "neg": f"@SP\nA=M-1\nM=-M",
}


def arith_comparison(counter, command):
    # uses a counter to make sure all the tags are unique
    branched_logic_comms = {
        "eq": f"{sub_comms['setup2vals']}\nD=D-M\n@EQ_TRUE_{counter}\nD;JEQ\nD=0\n@EQ_SAVE_{counter}\n0;JMP\n(EQ_TRUE_{counter})\nD=-1\n(EQ_SAVE_{counter})\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
        "gt": f"{sub_comms['setup2vals']}\nD=D-M\n@GT_TRUE_{counter}\nD;JGT\nD=0\n@GT_SAVE_{counter}\n0;JMP\n(GT_TRUE_{counter})\nD=-1\n(GT_SAVE_{counter})\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
        "lt": f"{sub_comms['setup2vals']}\nD=D-M\n@LT_TRUE_{counter}\nD;JLT\nD=0\n@LT_SAVE_{counter}\n0;JMP\n(LT_TRUE_{counter})\nD=-1\n(LT_SAVE_{counter})\n{sub_comms['dec2save']}\n{sub_comms['inc']}",
    }

    return branched_logic_comms[command]


def push_constant(constant):
    return f"@{constant}\nD=A\n@SP\nA=M\nM=D\n{sub_comms['inc']}"


def push_to_stack(segment: str, index: int):
    if segment == "temp":
        # push temp i
        # temp address is in RAM[5-12]
        # per spec, accessing temp i should result in accessing RAM[(5 + i)]
        # (said "RAM[*(5 + i)]" on slide, but reads like typo)
        result = (
            f"@{5+index}\n{sub_comms['push_val_in_D_to_stack']}\n{sub_comms['inc']}"
        )
    elif segment == "pointer":
        result = f"@{segments[segment][index]}\n{sub_comms['push_val_in_D_to_stack']}\n{sub_comms['inc']}"
    elif segment == "static":
        # push static i
        # creates variable: @vmtranslator.i
        # saves value directly in the variable's location
        result = f"@vmtranslator.{index}\n{sub_comms['push_val_in_D_to_stack']}\n{sub_comms['inc']}"
    else:
        # ex. push local index
        # goto location from segment address RAM[*segmentpointer]+index
        goto_pointer = f"@{index}\nD=A\n@{segments[segment]}\nA=D+M"

        # save value and push to stack
        result = (
            f"{goto_pointer}\n{sub_comms['push_val_in_D_to_stack']}\n{sub_comms['inc']}"
        )
    # print(result)
    return result


def pop_to_memory(segment: str, index: int):
    if segment == "temp":
        return f"@SP\nAM=M-1\nD=M\n@{5+index}\nM=D"
    elif segment == "static":
        return f"@SP\nAM=M-1\nD=M\n@vmtranslator.{index}\nM=D"
    elif segment == "pointer":
        return f"@SP\nAM=M-1\nD=M\n@{segments[segment][index]}\nM=D"
    else:
        calc_mem_location = f"@{index}\nD=A\n@{segments[segment]}\nD=D+M\n@R13\nM=D"
        # go to SP location and decrement SP
        get_from_stack = "@SP\nAM=M-1\nD=M"
        save_data_in_mem = "@R13\nA=M\nM=D"
        return f"{calc_mem_location}\n{get_from_stack}\n{save_data_in_mem}"


def function_definition(name: str, nVars: int):
    # TODO- do I need to include some disambiguation here like filename?
    # Or is it just the job of the coder to not use identical function names? Maybe...
    result = f"({name})"

    # initializing the local vars to 0 and incrementing SP
    for i in range(nVars):
        # push constant 0
        # partial_1 = push_constant(0)
        # # pop local i
        # # pop normally decrements SP so probably need to custom code this
        # partial_2 = pop_to_memory("local", i)
        # result += f"\n{partial_1}\n{partial_2}"

        # I can just use SP for this since it starts out the same as LCL and we want it incremented anyway
        result += f"\n@0\nD=A\n@SP\nA=M\nM=D\n{sub_comms['inc']}"

    return result


def return_command():
    """Handles all the required pieces of a return statement"""
    # store LCL mem value in @FRAME
    store_endframe = "@LCL\nD=M\n@FRAME\nM=D"
    # retrieve return address from (endframe - 5) location- store in RET
    store_retaddr = "@5\nD=A\n@FRAME\nA=M-D\nD=M\n@RET\nM=D"
    # ARG = pop() (pop top of stack and put val in ARG memory segment location)
    pop_to_arg = pop_to_memory(segment="argument", index=0)
    # reset stored pointer values back
    reset_sp = "@ARG\nD=M\n@SP\nM=D+1"
    reset_that = "@FRAME\nA=M-1\nD=M\n@THAT\nM=D"
    reset_this = "@2\nD=A\n@FRAME\nA=M-D\nD=M\n@THIS\nM=D"
    reset_arg = "@3\nD=A\n@FRAME\nA=M-D\nD=M\n@ARG\nM=D"
    reset_lcl = "@4\nD=A\n@FRAME\nA=M-D\nD=M\n@LCL\nM=D"

    # goto return address stored in @RET
    goto_retaddr = "@RET\nA=M\n0;JMP"

    result = f"{store_endframe}\n{store_retaddr}\n{pop_to_arg}\n{reset_sp}\n"
    result += f"{reset_that}\n{reset_this}\n{reset_arg}\n{reset_lcl}\n{goto_retaddr}"

    return result


# Main Logic
def translate_line(input: str, counter: int):
    """accepts single line of input, uses it to generate ASM code for the command"""

    element_list = re.split(" ", input)
    command = element_list[0]

    # write_arithmetic(command: str)
    if len(element_list) == 1:
        # arithmetic commands
        if command in ("eq", "gt", "lt"):
            return arith_comparison(counter, command)
        elif command == "return":
            return return_command()
        else:
            try:
                return arith_comms[command]
            except KeyError:
                raise KeyError(
                    f'{command} not found in arithmetic commands for input line "{input}" at count "{counter}"'
                )
    elif len(element_list) > 1:
        if len(element_list) == 2:
            # branching or label command
            label = element_list[1]

            if command == "label":
                return f"({label})"
            elif command == "goto":
                return f"@{label}\n0;JMP"
            elif command == "if-goto":
                # NOTE- spec wants the top stack value to be popped, not just read, when checked for the "if" here
                return f"{sub_comms['pop_top_stack_to_D']}\n@{label}\nD;JGT"

        elif len(element_list) == 3:
            # push or pop memory handling command
            arg1 = element_list[1]
            arg2int = int(element_list[2])

            # write_push_pop(command: str, segment: str, index: int)
            if command == "push":
                # push constant i
                if arg1 == "constant":
                    return push_constant(arg2int)
                # push segment i
                else:
                    return push_to_stack(arg1, arg2int)
            elif command == "pop":
                return pop_to_memory(arg1, arg2int)
            elif command == "function":
                return function_definition(name=arg1, nVars=arg2int)
    else:
        return ""


def translate_file(input_file, output_filename: str, counter: int):
    """
    Summary: translates entire file and writes output to specified output filename

    Args:
        input_file (file): .vm file to read
        output_filename (str): name of file to write into, will create new if doesn't exist and won't override existing lines
        counter (int): iterator to use as needed to prevent label overlap, also coincides with input line count for logs

    Return:
        counter (int): updated counter to keep iterating in next file as needed
    """
    with open(input_file, mode="r") as file:
        lines = [
            line.split("//")[0].strip(" \n\t")
            for line in file
            if line and (not line.isspace()) and (not line.startswith("//"))
        ]
    # loop through each line, ignoring white space and comments

    # filtered lines may output empty lines so need second filter round
    clean_lines = [line for line in lines if line and (not line.isspace())]

    with open(output_filename, "w") as output_file:
        for line in clean_lines:
            # print(f"in: {line}")
            # process each line with parser and code_writer
            output_line = translate_line(line, counter)
            counter = counter + 1

            # write final output string to output file '.asm'
            # if output_line:
            output_final_line = f"{output_line}\n"

            # print(f"out: {output_final_line}")
            output_file.write(output_final_line)

    return counter


def main(input_path):
    """Translates a provided '.vm' file or directory of files written in hack VM code
    into a '.asm' file in the hack assembly language.

    Args:
        input_path (str): input file 'filename.vm' or directory 'dirname' or 'dirname/'

    Returns:
        - generates and saves output file 'filename.asm'
    """
    pre, ext = os.path.splitext(input_path)
    output_filename = f"{pre}.asm"
    counter = 0

    # counter return is really to keep it iterating while ensuring scope stays clean
    counter = translate_file(input_path, output_filename, counter)

    # TODO- determine if working with one file or directory
    # If dir,
    # 1. add bootstrap code and
    # 2.loop through each .vm file

    return "DONE!"


if __name__ == "__main__":
    result = main(sys.argv[1])

    # print any return values to console for testing
    if result:
        print(result)
