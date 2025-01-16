from flask import Flask, request, render_template, jsonify
import os
from dotenv import load_dotenv
import requests
import json
from PIL import Image
import io
import base64
from openai import OpenAI
from google.cloud import vision
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import logging
import time
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__, template_folder='../templates')

# Initialize clients
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize Google Cloud Vision client
if os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
    # For Vercel deployment
    import json
    credentials_dict = json.loads(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
    credentials = vision.Credentials.from_service_account_info(credentials_dict)
    vision_client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    # For local development
    vision_client = vision.ImageAnnotatorClient()

ua = UserAgent()

def get_random_delay():
    return random.uniform(2, 5)

def search_movies(actor_name, max_retries=2):
    """Search for movies on javmost"""
    for attempt in range(max_retries + 1):
        try:
            # Format actor name for URL
            formatted_name = actor_name.replace(" ", "%20")
            url = f"https://www5.javmost.com/search/{formatted_name}"
            
            # Set up headers with random user agent
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Referer': 'https://www5.javmost.com/',
            }
            
            # Make the request
            logger.info(f"Searching movies for {actor_name} at {url} (Attempt {attempt + 1}/{max_retries + 1})")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all h4 tags with class card-title
            titles = soup.find_all('h4', class_='card-title m-t-0 m-b-10')
            
            # Extract movie codes
            movie_list = []
            for title in titles[:10]:  # Get first 10 titles
                movie_code = title.text.strip()
                # Remove -UNCENSORED-LEAK suffix if present
                movie_code = movie_code.replace('-UNCENSORED-LEAK', '')
                if movie_code:
                    movie_list.append(movie_code)
                    logger.info(f"Found movie code: {movie_code}")
            
            logger.info(f"Total movies found: {len(movie_list)}")
            
            # If we found movies, return them
            if movie_list:
                return movie_list
                
            # If no movies found and we have retries left, wait and try again
            if attempt < max_retries:
                time.sleep(get_random_delay())
                logger.info("No movies found, retrying...")
                continue
                
            # If we're out of retries, return empty list
            return []
            
        except Exception as e:
            logger.error(f"Error searching movies (Attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries:
                time.sleep(get_random_delay())
                continue
            return []

def analyze_image_with_vision(image_content):
    """Analyze image using Google Cloud Vision API"""
    try:
        # Create image object
        image = vision.Image(content=image_content)

        # Detect web entities and pages
        web_detection = vision_client.web_detection(image=image).web_detection
        
        # Detect faces
        face_detection = vision_client.face_detection(image=image).face_annotations
        
        # Get the best guess labels
        best_guess_labels = web_detection.best_guess_labels
        
        # Get web entities
        web_entities = web_detection.web_entities
        
        # Get visually similar images
        similar_images = web_detection.visually_similar_images
        
        # Combine results
        results = []
        
        # Add face detection results
        if face_detection:
            results.append("Face detected in image")
            # Add confidence score
            results.append(f"Face detection confidence: {face_detection[0].detection_confidence:.2f}")
        
        # Add best guess labels
        for label in best_guess_labels:
            results.append(f"Best guess: {label.label}")
            
        # Add web entities
        for entity in web_entities:
            if entity.description and entity.score:
                results.append(f"{entity.description} (score: {entity.score:.2f})")
                
        # Add URLs of similar images
        for image in similar_images[:5]:  # Limit to top 5 similar images
            if image.url:
                results.append(f"Similar image: {image.url}")
                
        return results
        
    except Exception as e:
        logger.error(f"Error in analyze_image_with_vision: {str(e)}")
        return []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        logger.info("Processing uploaded image...")
        
        # Read and process image
        img = Image.open(file)
        if img.mode in ('RGBA', 'LA'):
            logger.info(f"Converting image from {img.mode} to RGB")
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr = img_byte_arr.getvalue()
        
        # Analyze with Vision API
        logger.info("Starting Google Cloud Vision analysis...")
        vision_results = analyze_image_with_vision(img_byte_arr)
        vision_text = " ".join(vision_results)
        logger.info(f"Found {len(vision_results)} vision results")

        # Use OpenAI to identify the actor
        logger.info("Analyzing results with OpenAI...")
        actor_prompt = f"""Based on these image analysis results, who is the JAV actor/actress shown? 
        Only return their name in English (romaji). If you can't determine an actor/actress, return 'Unknown'.
        Analysis results: {vision_text}"""
        
        actor_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": actor_prompt}]
        )
        actor_name = actor_response.choices[0].message.content.strip()

        movies = []
        if actor_name != "Unknown":
            # Add random delay to avoid rate limiting
            time.sleep(get_random_delay())
            
            # Search for actor's movies
            logger.info(f"Searching for movies of {actor_name}...")
            movies = search_movies(actor_name)

        return jsonify({
            'actor_name': actor_name,
            'movies': movies,
            'analysis': vision_results
        })

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        return jsonify({'error': str(e)}), 500
