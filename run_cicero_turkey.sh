#!/bin/bash
# Script to run Cicero playing as Turkey in the Docker container

# Make sure Docker is running
echo "Checking Docker status..."
if ! docker ps > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker and try again."
  exit 1
fi

# Check if the container is already running
if ! docker-compose ps | grep "diplomacy" | grep "Up" > /dev/null; then
  echo "Starting Docker container..."
  docker-compose up -d
fi

# Create a temporary Python script content
SCRIPT_CONTENT='
#!/usr/bin/env python3
"""
Script to run Cicero playing as Turkey against imitation agents.
This demonstrates the recommended method using run.py with the proper config.
"""
import os
import sys
import subprocess
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def check_models():
    """Check if required model files are available."""
    model_dir = os.path.join(os.getcwd(), "models")
    if not os.path.exists(model_dir):
        logging.error("Models directory not found. Models need to be downloaded.")
        print("\nTo download models, you need to run:")
        print("bash bin/download_model_files.sh <PASSWORD>")
        print("The password is in the README: dbEmG*yo@fuWzb79cx_pN7.TRm4cqk")
        return False
    
    # Check for a few key model files
    required_models = [
        "cicero_imitation_bilateral_orders_prefix.ckpt",
        "cicero_imitation_orders.ckpt",
        "dialogue/20220729_dialogue_rolloutevery_replythresh_firstmessagethresh_5m.ckpt"
    ]
    
    missing = []
    for model in required_models:
        if not os.path.exists(os.path.join(model_dir, model)):
            missing.append(model)
    
    if missing:
        logging.error(f"Missing model files: {', '.join(missing)}")
        return False
    
    logging.info("All required model files found.")
    return True

def run_cicero_turkey():
    """Run Cicero as Turkey against imitation agents."""
    logging.info("Starting Cicero as Turkey in 1v6 game against imitation agents...")
    
    command = [
        "python", "run.py", "--adhoc", 
        "--cfg", "conf/c01_ag_cmp/cmp.prototxt", 
        "Iagent_one=agents/cicero.prototxt", 
        "Iagent_six=agents/ablations/cicero_imitation_only.prototxt", 
        "power_one=TURKEY",
        "num_trials=1",  # Just run one game
        "seed=42"        # For reproducibility
    ]
    
    logging.info(f"Running command: {' '.join(command)}")
    
    try:
        # Run the command and capture output
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Stream the output
        for line in process.stdout:
            print(line, end="")
        
        # Wait for process to complete
        process.wait()
        
        if process.returncode == 0:
            logging.info("Game completed successfully!")
            return True
        else:
            logging.error(f"Game failed with return code {process.returncode}")
            return False
            
    except Exception as e:
        logging.error(f"Error running game: {e}")
        return False

def main():
    """Main entry point."""
    print("=" * 80)
    print("CICERO PLAYING AS TURKEY")
    print("=" * 80)
    print("This will run Cicero (the FAIR/Meta Diplomacy AI) as Turkey")
    print("against 6 imitation agents using the recommended configuration.")
    print("\nThe game may take a while to run as it needs to load large models.")
    
    if not check_models():
        print("\nWARNING: Model files appear to be missing. The run will likely fail.")
        response = input("Do you want to continue anyway? (y/n): ")
        if response.lower() != "y":
            return
    
    print("\nStarting game... (this may take a few minutes to initialize)")
    run_cicero_turkey()
    
    print("\nGame log is saved in the experiment directory (check the output for the path)")
    print("You can view game results in the logs and the result.torch file")

if __name__ == "__main__":
    main()
'

# Run the command directly in the container
echo "Running Cicero as Turkey in the Docker container..."
docker-compose exec -T diplomacy bash -c "cat > /tmp/run_cicero_turkey.py << 'EOT'
$SCRIPT_CONTENT
EOT
chmod +x /tmp/run_cicero_turkey.py
python /tmp/run_cicero_turkey.py
rm /tmp/run_cicero_turkey.py"

echo "Script completed."