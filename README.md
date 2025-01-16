# Actor Name Finder

A web application that helps users identify actors from images and get their filmography information.

## Features
- Upload images of actors
- Automatic actor identification
- Get recent and best-rated filmography
- Modern, responsive UI

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a .env file in the root directory with your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

4. Run the application:
```bash
python app.py
```

5. Open your browser and navigate to `http://localhost:5000`

## Usage
1. Click the upload area or drag and drop an image
2. Click "Find Actor" button
3. View the results including actor name and filmography

## Requirements
- Python 3.8+
- OpenAI API key
- Internet connection for API calls
