
import subprocess

def run_js_script(code, input_string):
    try:
        # Call the parseSparql.js script with the input string
        subprocess.run(['node', code, input_string], check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred for the script: {e}")
        return False
    except FileNotFoundError:
        print("Node.js is not installed or parseSparql.js not found in the current directory")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    ### return a boolan to indicate if the script was run successfully
    return True