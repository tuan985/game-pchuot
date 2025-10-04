# Whack-a-Mole Hand Control Game

This project is a fun and interactive game called "Whack-a-Mole" that utilizes hand movements for control. Players can hit moles that pop up from holes using their hands, detected through OpenCV and MediaPipe.

## Project Structure

```
whack-a-mole-hand-control
├── src
│   ├── app.py            # Main entry point of the game
│   ├── hand_control.py   # Logic for hand movement detection
│   └── utils.py          # Utility functions for the game
├── assets
│   ├── background.png    # Background image for the game
│   ├── hole.png          # Image of the holes
│   ├── mole.png          # Image of the mole when visible
│   ├── hit_mole.png      # Image of the mole when hit
│   └── hammer.png        # Image of the hammer
├── requirements.txt      # List of dependencies
└── README.md             # Project documentation
```

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd whack-a-mole-hand-control
   ```

2. **Install dependencies**:
   It is recommended to use a virtual environment. You can create one using:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
   Then install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. **Run the game**:
   Execute the following command to start the game:
   ```
   python src/app.py
   ```

## Usage

- Use your hand to hit the moles that appear on the screen.
- The game tracks your score based on how many moles you hit within the time limit.

## Dependencies

This project requires the following Python packages:
- OpenCV
- MediaPipe
- Pygame

Make sure to install these packages as specified in the `requirements.txt` file.

## Acknowledgments

- This project utilizes OpenCV and MediaPipe for hand detection.
- Special thanks to the Pygame community for the game development framework.