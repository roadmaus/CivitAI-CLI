# Standard library imports
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from tempfile import NamedTemporaryFile
import imghdr
import emoji

# Related third-party imports
import inquirer
import requests
from PIL import Image
from bs4 import BeautifulSoup
from inquirer import Checkbox, List, Text, prompt, Confirm
from termcolor import colored
from tqdm import tqdm
from PIL import UnidentifiedImageError
from subprocess import Popen, PIPE
from colorama import Fore, Style

import signal
import sys

def signal_handler(sig, frame):
    print('Ctrl+C shutting down now.')
    os.system('cls' if os.name == 'nt' else 'clear')
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

class MainCLI:
    def __init__(self, model_display, settings_cli, downloader):
        self.model_display = model_display
        self.settings_cli = settings_cli
        self.downloader = downloader
        self.selected_models_to_download = []
        self.BASE_MODELS = ["SDXL 1.0", "SDXL 0.9", "SD 1.5","SD 1.4", "SD 2.0", "SD 2.0 768", "SD 2.1", "SD 2.1 768", "Other"]
        self.load_model_index()

    def main_menu(self):
        # Clear the terminal
        #os.system('cls' if os.name == 'nt' else 'clear')
        questions = [
            List('choice',
                 message="What would you like to do?",
                 choices=[
                     'List models',
                     'Fetch model by ID',
                     'Download model by ID',
                     'Scan for missing data',
                     'Resume interrupted Downloads' if self.selected_models_to_download else 'No interrupted downloads',
                     'Fetch model version by ID',
                     'Fetch model by Hash',
                     'Settings',
                     'Exit'],
                 )
        ]
        return prompt(questions)['choice']
    
    def load_model_index(self):
        try:
            with open('index.json', 'r') as f:
                self.model_index = json.load(f)
        except FileNotFoundError:
            self.model_index = {}
        return self.model_index  # Ensure that a dictionary is always returned 

    def scan_directory_for_models(self, directory):
        print("Scanning directory for downloaded models...")
        model_hashes = self.load_model_index()  # Load the existing index
        new_files_found = False
        directories_to_scan = [
            "models/Stable-diffusion",
            "embeddings",
            "models/hypernetworks",
            "extensions/stable-diffusion-webui-aesthetic-gradients/aesthetic_embeddings",
            "models/Lora",
            "models/Controlnet",
            "models/ESRGAN",
            "models/MotionModule",
            "models/VAE",
            "models/Poses",
            "models/Wildcards",
            "models/Workflows",
            "models/Other"
        ]
        for dir_to_scan in directories_to_scan:
            full_dir_path = os.path.join(directory, dir_to_scan)
            if os.path.exists(full_dir_path):
                for root, dirs, files in os.walk(full_dir_path):
                    for file in files:
                        _, ext = os.path.splitext(file)
                        if ext.lower() not in ['.ckpt', '.pt', '.safetensors']:
                            continue  # Skip this file if it doesn't have one of the desired extensions
                        model_id, _ = os.path.splitext(file)
                        model_file_path = os.path.join(root, file)  # Define model_file_path here
                        if any(model.get('filepath') == model_file_path and model.get('modelversionid') == model_id for model in model_hashes.values()):
                            continue  # Skip this model if it's already in the index
                        info_file_path = os.path.join(root, f'{model_id}.civitai.info')
                        model_modelId = None  # Initialize model_modelId to None
                        model_name = None  # Initialize model_name to None
                        model_hash = None  # Initialize model_hash to None
                        model_key = f"{model_id}_{model_file_path}"
                        model_hashes[model_key] = {"modelname": model_name, "modelid": model_modelId, "modelversionid": model_id, "hash": model_hash, "filepath": model_file_path}
                        if os.path.exists(info_file_path):
                            with open(info_file_path, 'r') as f:
                                info = json.load(f)
                                files = info.get('files', [])
                                if files:
                                    file_info = files[0]  # Assuming the relevant info is in the first item
                                    model_hash = file_info.get('hashes', {}).get('SHA256')
                                else:
                                    model_hash = None
                                model_id = info.get('id')
                                model_modelId = info.get('modelId')
                                model_name = info.get('model', {}).get('name')
                                print(f"Fetching hash from civitai.info for model {model_name}")
                                model_hashes[model_key] = {"modelname": model_name, "modelid": model_modelId, "modelversionid": model_id, "hash": model_hash, "filepath": model_file_path}
                        else:
                            for model in model_hashes.values():
                                if model.get('filepath') == model_file_path:
                                    break
                            else:
                                new_files_found = True
                                with open(model_file_path, 'rb') as f:
                                    model_data = f.read()
                                    model_hash = hashlib.sha256(model_data).hexdigest()
                                print(f"Generating hash for model {model_id}")
                                model_hashes[model_key] = {"modelname": model_name, "modelid": model_modelId, "modelversionid": model_id, "hash": model_hash, "filepath": model_file_path}
                for model_id in list(model_hashes.keys()):  # We use list() to avoid modifying the dictionary while iterating
                    model = model_hashes[model_id]
                    model_file_path = model.get('filepath')
                    if model_file_path and not os.path.exists(model_file_path):
                        del model_hashes[model_id]
        with open('index.json', 'w') as f:
            json.dump(model_hashes, f, indent=4)
        print("Finished scanning.")
        os.system('cls' if os.name == 'nt' else 'clear')
        return new_files_found


    def download_in_background(self):
        for model_id, version_id in self.selected_models_to_download:
            self.downloader.handle_multi_model_download_by_id(model_id, version_id, silent=True)
        self.selected_models_to_download = []  # Clear the list

    def fetch_model_by_id(self):
        questions = [
            Text('model_id',
                 message="Enter the model ID:")
        ]
        return prompt(questions)['model_id']

    def download_model_by_id(self):
        questions = [
            Text('model_id',
                 message="Enter the model ID:")
        ]
        return prompt(questions)['model_id']

    def list_models_menu(self):
        current_page = 1
        reload_page = True 
        temporary_query = None
        #os.system('cls' if os.name == 'nt' else 'clear')
        while True:
            if reload_page:
                if temporary_query:
                    query = {**temporary_query, 'page': current_page}
                else:
                    query = {**self.model_display.default_query, 'page': current_page}
                models, metadata = self.settings_cli.api_handler.get_models_with_default_query(query)
                if metadata is None or 'error' in metadata:
                    print("Error fetching models:", metadata.get('error', 'Unknown error'))
                    return
                total_pages = metadata.get('totalPages', 1)  # Initialize total pages

                # Display the fetched models
                for model in models:
                    model_id = model.get('id')
                    #print(f"DEBUG: Checking model with ID: {model_id}")  # Debug statement
                    downloaded_versions = []  # List to store downloaded versions
                    model_versions = model.get('modelVersions', [])
                    for index_model in self.model_index.values():
                        if index_model['modelid'] == model_id:
                            for version in model_versions:
                                if index_model['modelversionid'] == version.get('id'):
                                    # This is a downloaded version
                                    downloaded_versions.append(version.get('name'))
                    download_status = None
                    if downloaded_versions:
                        # If downloaded versions were found
                        if len(downloaded_versions) < len(model_versions):
                            # If there are more versions available than downloaded
                            if len(downloaded_versions) == 1:
                                download_status = f"{Fore.YELLOW}⚠️ MORE VERSIONS AVAILABLE. Version '{', '.join(downloaded_versions)}' is downloaded.{Style.RESET_ALL}"
                            else:
                                download_status = f"{Fore.YELLOW}⚠️ MORE VERSIONS AVAILABLE. Versions '{', '.join(downloaded_versions)}' are downloaded.{Style.RESET_ALL}"
                        else:
                            # If all versions are downloaded
                            if len(downloaded_versions) == 1:
                                download_status = f"{Fore.GREEN}✅ ALL VERSIONS DOWNLOADED. Version '{', '.join(downloaded_versions)}' is downloaded.{Style.RESET_ALL}"
                            else:
                                download_status = f"{Fore.GREEN}✅ ALL VERSIONS DOWNLOADED. Versions '{', '.join(downloaded_versions)}' are downloaded.{Style.RESET_ALL}"
                    self.model_display.display_model_card(model, self.settings_cli.image_filter, download_status, self.settings_cli.image_filter_settings)
                reload_page = False
                

            pagination_choices = ['Next page', 'Previous page', 'Jump to page'] if total_pages > 1 else []
            menu_question = [
                List('action',
                     message=f'What would you like to do? {f"(Current Page: {current_page}/{total_pages})" if total_pages > 1 else ""}',
                     choices=pagination_choices + [
                         'Filter this search',
                         'Search Model',
                         'Select to Download',
                         'Initiate Download',
                         'Initiate Background Download',
                         'Select for more Info',
                         'Back to main menu'
                     ])
            ]
            menu_answer = prompt(menu_question)
            action = menu_answer['action']

            total_pages = metadata.get('totalPages', 1)

            if action == 'Next page':
                if current_page < total_pages:
                    current_page += 1
                    #print("Debug: Current Page updated to ", current_page)
                    reload_page = True
                else:
                    print("You're already on the last page.")

            elif action == 'Previous page':
                if current_page > 1:
                    current_page -= 1
                    #print("Debug: Current Page updated to ", current_page)
                    reload_page = True
                else:
                    print("You're already on the first page.")

            elif action == 'Jump to page':
                jump_question = [
                    Text('page_number',
                         message=f"Enter the page number (1-{total_pages}):")
                ]
                jump_answer = prompt(jump_question)
                page_number = int(jump_answer['page_number'])
                if 1 <= page_number <= total_pages:
                    current_page = page_number
                    reload_page = True
                else:
                    print(f"Invalid page number. Please enter a number between 1 and {total_pages}.")

            if action == 'Filter this search':
                # Display current values either from the temporary query or from the default query
                current_values = temporary_query if temporary_query else self.model_display.default_query
                print(f"Current filter settings: {current_values}")
                current_page = 1 

                temporary_query = self.settings_cli.set_default_query(is_temporary=True, current_query=temporary_query)
                reload_page = True

            elif action == 'Search Model':
                search_question = [
                    Text('model_name',
                         message="Enter the model name to search:")
                ]
                search_answer = prompt(search_question)
                model_name = search_answer.get('model_name', '')
                
                # Create a new base query only for search
                search_query = {'query': model_name}
                temporary_query = search_query  # Set the temporary query to the search query
                current_page = 1 
                # Call your API with this query
                models, metadata = self.settings_cli.api_handler.get_models_with_default_query(search_query)
                if metadata is None or 'error' in metadata:
                    print("Error fetching models:", metadata.get('error', 'Unknown error'))
                    return
                # Update total pages based on the metadata received from the search query
                total_pages = metadata.get('totalPages', 1)  # <-- Add this line
                # Display the fetched models
                for model in models: 
                    # Access image_filter from settings_cli and pass it to display_model_card
                    self.model_display.display_model_card(model, self.settings_cli.image_filter, download_status, self.settings_cli.image_filter_settings)
                    # Debug: Print image_filter value
                    #print(f"DEBUG: Current image_filter = {self.settings_cli.image_filter}")

                reload_page = False

            elif action == 'Select to Download':
                reload_page = False
                # Prepare choices based on currently displayed models
                choices = [
                    (model.get('name', 'Unknown'), model.get('id', None))
                    for model in models
                ]
                choices.append(('Back', None))  # Add 'Back' option
                download_question = [
                    Checkbox('selected_models',
                            message='Which models would you like to download?',
                            choices=choices)
                ]
                download_answer = prompt(download_question)
                selected_model_ids = download_answer.get('selected_models', [])
                if 'Back' in selected_model_ids:
                    continue  # Continue to the next iteration of the outer loop if 'Back' is selected
                if selected_model_ids:
                    for model_id in selected_model_ids:
                        model = self.settings_cli.api_handler.get_model_by_id(model_id)
                        model_versions = model.get('modelVersions', [])
                        
                        # Fetch downloaded versions for the current model
                        downloaded_versions = []  # List to store downloaded versions
                        for index_model in self.model_index.values():
                            if index_model['modelid'] == model_id:
                                for version in model_versions:
                                    if index_model['modelversionid'] == version.get('id'):
                                        # This is a downloaded version
                                        downloaded_versions.append(version.get('name'))

                        if len(model_versions) > 1:
                            version_choices = []
                            for ver in model_versions:
                                version_name = ver.get('name', 'Unknown')
                                version_id = ver.get('id', None)
                                # Check if this version is already downloaded
                                if version_name in downloaded_versions:
                                    version_name += " (downloaded)"
                                version_choices.append((version_name, version_id))
                            version_choices.append(('Back', None))  # Add 'Back' option
                            version_question = [
                                Checkbox('selected_versions',
                                        message=f'Select versions for {model.get("name", "Unknown")}',
                                        choices=version_choices)
                            ]
                            version_answer = prompt(version_question)
                            selected_version_ids = version_answer.get('selected_versions', [])
                            if selected_version_ids:
                                if 'Back' in selected_version_ids:
                                    break  # Break out of the loop if 'Back' is selected
                                for version_id in selected_version_ids:
                                    self.selected_models_to_download.append((model_id, version_id))
                        elif len(model_versions) == 1:
                            # Automatically add the single version to the download list
                            single_version = model_versions[0]
                            single_version_id = single_version.get('id', None)
                            self.selected_models_to_download.append((model_id, single_version_id))
                            print(f"Automatically selected version {single_version.get('name', 'Unknown')} for {model.get('name', 'Unknown')} for download.")
                        else:
                            print(f"No versions available for {model.get('name', 'Unknown')}. Skipping.")
                                                    
                    print("\033[94m\033[1mModels and versions selected for download. Continue browsing or initiate download.\033[0m")  # Blue and bold
                    continue

            elif action == 'Initiate Background Download':
                reload_page = False
                if self.selected_models_to_download:
                    download_thread = threading.Thread(target=self.download_in_background)
                    download_thread.start()
                    print("\033[92m\033[1mStarted downloading models in the background.\033[0m")
                else:
                    print("\033[91m\033[1mNo models to download. Please select some first.\033[0m")  


            elif action == 'Initiate Download':
                reload_page = False
                if self.selected_models_to_download:
                    for model_id, version_id in self.selected_models_to_download:
                        self.downloader.handle_multi_model_download_by_id(model_id, version_id, silent=False)
                    self.selected_models_to_download = []  # Clear the list after downloading
                    print("All selected models have been downloaded.")
                else:
                    print("No models to download. Please select some first.")


            elif action == 'Select for more Info':
                # Prepare choices based on currently displayed models
                choices = [
                    (model.get('name', 'Unknown'), model.get('id', None))
                    for model in models  
                ]
                
                info_question = [
                    Checkbox('selected_models',
                             message='Which models would you like to know more about?',
                             choices=choices)
                ]
                
                info_answer = prompt(info_question)
                selected_model_ids = info_answer.get('selected_models', [])
                
                if selected_model_ids:
                    for model_id in selected_model_ids:
                        # Use your actual method to fetch more info here.
                        model_version = self.settings_cli.api_handler.get_model_by_id(model_id)
                        if model_version:
                            self.model_display.display_model_version_details(model_version, self.settings_cli.image_filter)
                        else:
                            print(f"No detailed information available for model ID: {model_id}")
                else:
                    print("No models selected for more information.")




            elif action == 'Back to main menu':
                temporary_query = None  # Resetting the temporary query
                #print("Debug: Cleared temporary_query")  # Debug statement
                break

    def download_metadata_menu(self):
        questions = [
            List('choice',
                 message="Download meta Data for existing models:",
                 choices=[
                     'For specific model',
                     'Overwrite all'],
                 )
        ]
        return prompt(questions)['choice']

    def fetch_model_version_by_id(self):
        questions = [
            Text('model_version_id',
                 message="Enter the model version ID:")
        ]
        return prompt(questions)['model_version_id']

    def fetch_model_by_hash(self):
        questions = [
            Text('hash',
                 message="Enter the model hash:")
        ]
        return prompt(questions)['hash']

    def scan_for_missing_data_menu(self):
        # Load the existing index
        model_hashes = self.load_model_index()

        # Check if all indexed files have a model id
        all_files_have_model_id = all(model.get('modelid') for model in model_hashes.values())

        if all_files_have_model_id:
            # If all indexed files have a model id, inform the user that all files are up-to-date
            print("All files are up-to-date.")
        else:
            # If any indexed file does not have a model id, start the process of finding and creating new metadata
            # Create an interactive menu for folder selection
            choices = list(downloader.type_to_path.keys())
            filtered_choices = [choice for choice in choices if choice not in ["Workflows", "Other", "Poses", "MotionModule"]]
            sorted_choices = ['All'] + sorted(filtered_choices)

            questions = [
                List('folder_choice',
                     message="Select folders to scan for missing data:",
                     choices=sorted_choices,
                     )
            ]
            folder_choice = prompt(questions)['folder_choice']

            # Translate 'All' to None, to scan all folders
            if folder_choice == 'All':
                downloader.scan_and_update_metadata()  # Pass None implicitly
            else:
                # Get the actual folder path from type_to_path
                folder_choice = downloader.type_to_path.get(folder_choice)
                downloader.scan_and_update_metadata(folders=[folder_choice])

            # After creating new metadata, update the index
            self.scan_directory_for_models(self.downloader.default_download_dir)


    def refresh_downloader_settings(self):
        self.downloader.default_download_dir = self.settings_cli.root_directory
        print(f"Downloader settings refreshed. New root directory is {self.downloader.default_download_dir}.")

class SettingsCLI:
    BASE_MODELS = ["SDXL 1.0", "SDXL 0.9", "SD 1.5", "SD 1.4", "SD 2.0", "SD 2.0 768", "SD 2.1", "SD 2.1 768", "Other"]
    MODEL_TYPES = ["Checkpoint", "TextualInversion", "Hypernetwork", "AestheticGradient", "LORA", "LoCon", "Controlnet", "Poses", "Upscaler", "MotionModule", "VAE", "Poses", "Wildcards", "Workflows", "Other"]
    SORT_OPTIONS = ["Highest Rated", "Most Downloaded", "Newest"]
    PERIOD_OPTIONS = ["AllTime", "Year", "Month", "Week", "Day"]
    ALLOW_COMMERCIAL_USE = ["None", "Image", "Rent", "Sell"]    
    def __init__(self, api_handler, model_display, current_temporary_filter=None):
        self.api_handler = api_handler
        self.model_display = model_display
        self.model_version_preference = 'primary'  # Initialize here
        self.load_settings()
        self.load_query_settings()
        self.image_filter_settings = {'nsfw_status': 'allow'} 

    def load_query_settings(self):
        try:
            with open('query_settings.json', 'r') as f:
                self.model_display.default_query = json.load(f)
            #print("Loaded query settings:", self.model_display.default_query)
        except FileNotFoundError:
            self.model_display.default_query = {}
            print("No query settings file found. Using default settings.")

    def validate_image_filter(self, image_filter):
        nsfw_types = ['Soft', 'Mature', 'X']
        actions = ['allow', 'block', 'blockify']
        if not isinstance(image_filter, dict):
            return False
        for nsfw_type, action in image_filter.items():
            if nsfw_type not in nsfw_types or action not in actions:
                return False
        return True

    def load_settings(self):
        try:
            with open('settings.json', 'r') as f:
                settings = json.load(f)
            self.model_display.text_only = settings.get('text_only', False)
            self.model_display.size = settings.get('size', 'medium')
            self.image_filter = settings.get('image_filter', {'Soft': 'allow', 'Mature': 'block', 'X': 'blockify'})
            if not self.validate_image_filter(self.image_filter):
                print("Warning: Invalid image filter settings found. Using default settings.")
                self.image_filter = {'Soft': 'blockify', 'Mature': 'block', 'X': 'block'}
            #print(f"DEBUG: Loaded image_filter = {self.image_filter}")  # Debug print
            self.root_directory = settings.get('root_directory', os.path.join(os.path.expanduser("~"), 'Downloads'))
        except FileNotFoundError:
            print("Settings file not found. Using default settings.")
            self.image_filter = {'Soft': 'blockify', 'Mature': 'block', 'X': 'block'}
            self.root_directory = os.path.join(os.path.expanduser("~"), 'Downloads')

    def settings_menu(self):
        while True:
            questions = [
                List('choice',
                     message="Settings Menu",
                     choices=[
                         'Change display mode',
                         'Adjust image size',
                         'Set default query',
                         'Set image filter',
                         'Set root directory',
                         'Back to main menu'],
                     )
            ]
            choice = prompt(questions)['choice']
            
            action_map = {
                'Change display mode': self.change_display_mode,
                'Adjust image size': self.adjust_image_size,
                'Set default query': self.set_default_query,
                'Set image filter': self.set_image_filter,
                'Set root directory': self.set_root_directory,
                'Back to main menu': self.exit_menu,
            }
            
            action = action_map.get(choice)
            if action:
                action()

            if choice == 'Back to main menu':
                print("Exiting settings menu. Have a great day!")
                break  
    
    def set_default_query(self, is_temporary=False, current_query=None):
        query_to_update = current_query if current_query else self.model_display.default_query
        default_query = query_to_update.copy()
        action_question = List('action',
                               message='Here, you can modify the default search filter or create a new one.',
                               choices=['Edit', 'New'])
        action_ans = prompt([action_question])['action']
        # Check for API key in environment variables
        has_api_key = 'CIVITAI_API_KEY' in os.environ

        if action_ans == 'New':
            self.model_display.default_query = {}
            default_query = {}  # Also clear the local copy
            print("Cleared the default query. You can now create a new one.")

        # Limit (number)
        limit_question = Text('limit', message=f'How many results would you like per page? (Current: {default_query.get("limit", "100")})')
        limit_ans = prompt([limit_question])['limit']
        if limit_ans:
            default_query['limit'] = int(limit_ans)

        for q_param, description in [("query", "models by a specific name"), ("tag", "models by a specific tag"), ("username", "models by a specific user")]:
            question = Text(q_param, message=f'Do you want to filter {description}? (Current: {default_query.get(q_param, "Not Set")}, press space to clear)')
            ans = prompt([question])[q_param]
            if ans == " ":
                default_query.pop(q_param, None)  # Remove the key if it exists
            elif ans:
                default_query[q_param] = ans

        # Types, Sort, Period, AllowCommercialUse (enum)
        for q_param, choices, description in [("types", self.MODEL_TYPES, "types of models"), ("sort", self.SORT_OPTIONS, "sort the models"), ("period", self.PERIOD_OPTIONS, "time frame"), ("allowCommercialUse", self.ALLOW_COMMERCIAL_USE, "commercial permissions")]:
            current_value = default_query.get(q_param, "Not Set")
            question = List(q_param, message=f'Which {description} are you interested in? (Current: {current_value})', choices=['No Change', 'Clear'] + choices, default='No Change')

            ans = prompt([question])[q_param]
            if ans == 'Clear':
                default_query.pop(q_param, None)
            elif ans != 'No Change':
                default_query[q_param] = ans

        # Booleans (Favorites, Hidden, etc.) only if API key exists
        if has_api_key:
            for q_param, description in [("favorites", "favorites of the authenticated user"), ("hidden", "hidden models of the authenticated user")]:
                current_value = default_query.get(q_param, "Not Set")
                question = Confirm(q_param, message=f'Do you want to filter {description}? (Current: {current_value})', default=current_value if current_value != "Not Set" else None)
                ans = prompt([question])[q_param]
                default_query[q_param] = ans

        # Base Model (with custom logic)
        current_base_model = default_query.get('base_model', "Not Set")
        base_model_choices_with_current = [f'[Current] {current_base_model}', 'No Change', 'Clear'] + [choice for choice in self.BASE_MODELS if choice != current_base_model]
        base_model_question = List('base_model', message=f'Which base model are you interested in? (Current: {current_base_model})', choices=base_model_choices_with_current, default=f'[Current] {current_base_model}' if current_base_model != "Not Set" else 'No Change')
        base_model_ans = prompt([base_model_question])['base_model']
        if base_model_ans == 'Clear':
            default_query.pop('base_model', None)
        elif base_model_ans != 'No Change':
            default_query['base_model'] = base_model_ans

        # Determine the current NSFW setting
        current_nsfw = default_query.get('nsfw', 'All')
        if current_nsfw is True:
            current_nsfw = 'NSFW'
        elif current_nsfw is False:
            current_nsfw = 'SFW'
        else:
            current_nsfw = 'All'

        # Using the current setting in the question message
        nsfw_question = List('content_filter',
                             message=f'Do you want to filter content? (Current: {current_nsfw})',
                             choices=['No Change', 'Clear', 'All', 'NSFW', 'SFW'],
                             default='No Change')

        # Fetch the answer
        nsfw_ans = prompt([nsfw_question])['content_filter']

        # Update the default_query based on the user's choice
        if nsfw_ans == 'Clear':
            default_query.pop('nsfw', None)
        elif nsfw_ans == 'NSFW':
            default_query['nsfw'] = True
        elif nsfw_ans == 'SFW':
            default_query['nsfw'] = False

        # Save the updated query
        if is_temporary:
            return default_query
        else:
            self.model_display.default_query = default_query
            self.save_query_settings()

    def set_image_filter(self):
        nsfw_types = ['Soft', 'Mature', 'X']  # NSFW categories
        actions = ['Allow', 'Block', 'Blockify']  # Possible actions
        
        image_filter_settings = {}  # To store user preferences
        
        print("Choose an action for the following content types:")
        for nsfw_type in nsfw_types:
            print(f"{nsfw_type} Content:")
            for i, action in enumerate(actions, 1):
                print(f"    [{i}] {action}")
            
            # Capture user choice and ensure it is valid
            while True:
                try:
                    user_choice = int(input(f"Your choice for {nsfw_type} content (1/2/3): "))
                    if user_choice not in [1, 2, 3]:
                        raise ValueError("Invalid choice")
                    image_filter_settings[nsfw_type] = actions[user_choice - 1].lower()
                    break  # Exit the loop if input is valid
                except ValueError as e:
                    print(e)
                    print("Invalid input. Please choose 1, 2, or 3.")
        
        # Save settings
        self.image_filter = image_filter_settings
        self.save_settings()
        print("Image filter settings have been changed.")


    def set_root_directory(self):
        questions = [
            Text('root_directory', message='Enter your preferred root directory:')
        ]
        answers = prompt(questions)
        if 'root_directory' in answers:
            self.root_directory = answers['root_directory']
            self.save_settings()
            print("Root directory changed. Updating model index...")
            main_cli.refresh_downloader_settings()
            main_cli.scan_directory_for_models(self.root_directory)
            print("Model index updated.")

    def change_display_mode(self):
        questions = [
            List('choice',
                 message="Choose display mode:",
                 choices=['Text Only', 'With Images'],
                 )
        ]
        choice = prompt(questions)['choice']
        self.model_display.text_only = (choice == 'Text Only')
        self.save_settings()
        print(f"Display mode changed to {choice}.")
    
    def adjust_image_size(self):
        questions = [
            List('choice',
                 message="Choose image size:",
                 choices=['Small', 'Medium', 'Large'],
                 )
        ]
        choice = prompt(questions)['choice']
        self.model_display.size = choice.lower()
        self.save_settings()
        print(f"Image size changed to {choice}.")
    
    def save_settings(self):
        settings = {
            'text_only': self.model_display.text_only,
            'size': self.model_display.size,
            #'model_version_preference': self.model_version_preference,  
            'root_directory': self.root_directory,
            'image_filter': self.image_filter
        }
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
        print("Settings saved successfully.")
 
    def save_query_settings(self):
        with open('query_settings.json', 'w') as f:
            json.dump(self.model_display.default_query, f)
        print("Query settings saved successfully.")

    def exit_menu(self):
        #print("Exiting settings menu. Have a great day!")
        return


    # Mock methods for new features
    def api_endpoint_configuration(self):
        pass

    def api_key_management(self):
        pass

class APIHandler:
    BASE_URL = 'https://civitai.com/api/v1/'

    def preprocess_query(self, query_dict):
        for key, value in query_dict.items():
            if isinstance(value, bool):
                query_dict[key] = str(value).lower()
            elif key == 'types' and isinstance(value, list):
                query_dict[key] = ','.join(value)
        return query_dict


    def get_models(self):
        query = self.model_display.default_query if hasattr(self.model_display, 'default_query') else {}
        endpoint = f"{self.BASE_URL}models"
        
        max_retries = 10  # Maximum number of retries
        retry_count = 0  # Initialize retry count

        while retry_count < max_retries:
            response = requests.get(endpoint, allow_redirects=False)
            #print("Status Code:", response.status_code)
            #print("Raw Response:", response.text)
            
            if response.status_code == 200:
                try:
                    return response.json()  # Attempt to parse the JSON
                except json.JSONDecodeError:  # Catch the JSON decoding error
                    print("CivitAI has trouble at the moment")
                    return None, {'error': 'Invalid JSON response'}
                
            elif 400 <= response.status_code < 500:
                return None, {'error': f"Client error: {response.content.decode('utf-8')}"}
                
            elif 500 <= response.status_code < 600:
                print(f"Server error occurred. Retrying... {retry_count + 1}/{max_retries}")
                retry_count += 1
                time.sleep(2)  # Wait for 2 seconds before retrying
                
            else:
                return None, {'error': f"An unknown error occurred. Status Code: {response.status_code}"}

        return None, {'error': 'Max retries reached. Please try again later.'}

    def post_process_filter(self, api_results, base_model=None, nsfw_only=False):
        # Initialize an empty list to store the filtered results
        filtered_results = []

        for model in api_results:
            # Initialize a flag for each model, set to True initially
            add_model = True

            # Check for base model
            if base_model:
                model_versions = model.get('modelVersions', [])
                if not any(version.get('baseModel') == base_model for version in model_versions):
                    add_model = False

            # Check for NSFW-only content
            if nsfw_only:
                if model.get('nsfw') is not True:
                    add_model = False

            # If the flag is still True, add the model to the filtered list
            if add_model:
                filtered_results.append(model)

        return filtered_results


    def get_models_with_default_query(self, default_query_dict, override_query_dict=None):
        api_key = os.environ.get('CIVITAI_API_KEY')
        headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
        query_dict = default_query_dict.copy()
        if override_query_dict:
            query_dict.update(override_query_dict)

        # Preprocess the query
        query_dict = self.preprocess_query(query_dict)
        #print("Debug: Final query to API: ", query_dict)
        endpoint = f"{self.BASE_URL}models"
        #print(f"DEBUG: Calling API URL {endpoint} with query {query_dict}")

        max_retries = 5  # Maximum number of retries
        retry_count = 0  # Initialize retry count

        while retry_count < max_retries:
            response = requests.get(endpoint, params=query_dict, headers=headers, allow_redirects=False)
            #print("Status Code:", response.status_code)

            if response.status_code == 200:
                #print("DEBUG: Successful API call to get_models_with_default_query.")
                api_results = response.json()
                base_model = query_dict.get('base_model')
                nsfw_only = query_dict.get('nsfw') == 'true'
                filtered_results = self.post_process_filter(api_results['items'], base_model, nsfw_only)
                return filtered_results, api_results.get('metadata', {})

            elif 400 <= response.status_code < 500:
                return None, {'error': f"Client error: {response.content.decode('utf-8')}"}

            elif 500 <= response.status_code < 600:
                print(f"Server error occurred. Retrying... {retry_count + 1}/{max_retries}")
                retry_count += 1
                time.sleep(2)  # Wait for 2 seconds before retrying

            else:
                return None, {'error': f"An unknown error occurred. Status Code: {response.status_code}"}

        return None, {'error': 'Max retries reached. Please try again later.'}

    def get_model_by_id(self, model_id):
        endpoint = f"{self.BASE_URL}models/{model_id}"
        response = requests.get(endpoint, allow_redirects=False)
        #print("Status Code:", response.status_code)
        return response.json() if response.status_code == 200 else None

    def get_model_version_by_id(self, version_id):
        endpoint = f"{self.BASE_URL}model-versions/{version_id}"
        response = requests.get(endpoint, allow_redirects=False)
        #print("Status Code:", response.status_code)
        return response.json() if response.status_code == 200 else None

    def get_model_by_hash(self, hash_value):
        endpoint = f"{self.BASE_URL}model-versions/by-hash/{hash_value}"
        response = requests.get(endpoint, allow_redirects=False)
        #print("Status Code:", response.status_code)
        return response.json() if response.status_code == 200 else None  

class Downloader:
    def __init__(self, api_handler, settings_cli, main_cli, root_directory=None):
        self.settings_cli = settings_cli
        self.main_cli = main_cli
        self.api_handler = api_handler
        self.root_directory = root_directory
        self.failed_downloads_list = []
        self.type_to_path = {
            "Checkpoint": "models/Stable-diffusion",
            "TextualInversion": "embeddings",
            "Hypernetwork": "models/hypernetworks",
            "AestheticGradient": "extensions/stable-diffusion-webui-aesthetic-gradients/aesthetic_embeddings",
            "LORA": "models/Lora",
            "LoCon": "models/Lora",
            "Controlnet": "models/Controlnet",
            "Upscaler": "models/ESRGAN",
            "MotionModule": "models/MotionModule",
            "VAE": "models/VAE",
            "Poses": "models/Poses",
            "Wildcards": "models/Wildcards",
            "Workflows": "models/Workflows",
            "Other": "models/Other"
        }

        self.MAX_RETRIES = 3  # Maximum number of retries
        self.RETRY_DELAY = 5  # Delay in seconds between retries        
        self.default_download_dir = root_directory or os.path.join(os.path.expanduser("~"), 'Downloads')
        print(colored(f"🚀 Downloader initialized with root directory {self.default_download_dir}", "green"))

    @staticmethod
    def format_html_to_text(html_content):
        if html_content is None:
            return "N/A"
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text()

    def map_sd_version(self, base_model):
        mapping = {
            "SD 1.4": "SD1",
            "SD 1.5": "SD1",
            "SD 2.0": "SD2",
            "SD 2.0 768": "SD2",
            "SD 2.1": "SD2",
            "SD 2.1 768": "SD2",
            "SDXL 0.9": "SDXL",
            "SDXL 1.0": "SDXL",
            "Other": "Unknown"
        }
        return mapping.get(base_model, "Unknown")

    def get_download_path(self, model_type):
        # Determine the download path based on the model type
        path = os.path.join(self.default_download_dir, self.type_to_path.get(model_type, 'Unknown'))
        #print(f"Debug: get_download_path returns {path}")
        return path

    def handle_model_download_by_id(self, model_id, silent=False):
        try:
            model = self.api_handler.get_model_by_id(model_id)
        except requests.exceptions.RequestException as e:
            print(f"Failed to get model by ID {model_id}. Error: {e}")
            self.failed_downloads_list.append({'type': 'Unknown', 'version_id': model_id})
            return
        
        if not model:
            print(f"Could not fetch model with ID: {model_id}")
            return

        model_type = model.get('type', 'Unknown')
        download_path = self.get_download_path(model_type)
        model_versions = model.get('modelVersions', [])

        if len(model_versions) == 1:
            single_version = model_versions[0]
            model_version_id = single_version.get('id', None)
            model_version_download_url = single_version.get('downloadUrl', None)

            if model_version_id and model_version_download_url:
                self.download_model_by_id(model_version_id, download_path, model_type, silent)
            else:
                print("Model ID or download URL is not available.")

        elif len(model_versions) > 1:
            choices = [
                (f"{model.get('name', 'Unknown')} - {ver.get('name', 'Unknown')}", 
                 {'id': ver.get('id', None), 'downloadUrl': ver.get('downloadUrl', None)})
                for ver in model_versions
            ]
            questions = [
                inquirer.Checkbox('versions',
                                  message="Which versions would you like to download?",
                                  choices=choices,
                                  ),
            ]
            answers = inquirer.prompt(questions)

            for selected_version in answers.get('versions', []):
                model_version_id = selected_version.get('id', None)
                model_version_download_url = selected_version.get('downloadUrl', None)

                if model_version_id and model_version_download_url:
                    self.download_model_by_id(model_version_id, download_path, model_type, silent)
                else:
                    print(f"Model ID or download URL for version ID {model_version_id} is not available.")

        else:
            print("No versions available for this model.")


    def handle_multi_model_download_by_id(self, model_id, version_id, silent=False):
        for attempt in range(self.MAX_RETRIES):
            try:
                model = self.api_handler.get_model_by_id(model_id)
                break  # If the model is fetched successfully, break out of the loop
            except requests.exceptions.RequestException as e:
                print(f"Failed to get model by ID {model_id} on attempt {attempt + 1}. Error: {e}")
                # If it's not the last attempt, wait a bit before retrying
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                else:  
                    # If it's the last attempt, log the failure and return
                    self.failed_downloads_list.append({'type': 'Unknown', 'version_id': model_id})
                    return

        if not model:
            print(f"Could not fetch model with ID: {model_id}")
            return

        model_type = model.get('type', 'Unknown')
        download_path = self.get_download_path(model_type)
        model_versions = model.get('modelVersions', [])

        if model_versions:
            selected_version = next((v for v in model_versions if v.get('id') == version_id), None)
            if selected_version:
                model_version_id = selected_version.get('id', None)
                model_version_download_url = selected_version.get('downloadUrl', None)

                if model_version_id and model_version_download_url:
                    self.download_model_by_id(model_version_id, download_path, model_type, silent)
                else:
                    print("Model ID or download URL is not available.")
        else:
            print("No versions available for this model.")

    @staticmethod
    def spinning_cursor():
        global spin
        spinner = "|/-\\"
        i = 0
        while spin:
            print(f"   Downloading... {spinner[i % len(spinner)]}", end="\r", flush=True)
            time.sleep(0.2)
            i += 1
        print("   Download complete!", end="\r", flush=True)
        
    def download_model_by_id(self, model_version_id, final_download_path, model_type, silent=True, failed_downloads_list=None):
        try:
            global spin
            with tempfile.TemporaryDirectory() as temp_dir:
                aria2_command = [
                    "aria2c",
                    f"https://civitai.com/api/download/models/{model_version_id}",
                    "--dir", temp_dir,
                    "--content-disposition"
                ]
                
                if silent:
                    process = Popen(aria2_command, stdout=PIPE, stderr=PIPE)
                    process = Popen(aria2_command, stdout=PIPE, stderr=PIPE)
                    stdout, stderr = process.communicate()
                    print(f"stdout: {stdout.decode('utf-8')}")
                    print(f"stderr: {stderr.decode('utf-8')}")
                else:
                    # Start the spinner in a separate thread
                    spin = True
                    spinner_thread = threading.Thread(target=self.spinning_cursor)
                    spinner_thread.start()

                    # Redirect aria2's output to a log file
                    with open("aria2_output.log", "w") as f:
                        process = Popen(aria2_command, stdout=f, stderr=f)
                        process.wait()

                    # Stop the spinner when the download is done
                    spin = False

                    # Wait for the spinner to stop
                    spinner_thread.join()
                
                # Assume the temporary directory now contains one file, the downloaded file.
                # Get its name
                downloaded_files = os.listdir(temp_dir)
                if downloaded_files:
                    downloaded_file_name = downloaded_files[0]
                    downloaded_file_path = os.path.join(temp_dir, downloaded_file_name)
                    
                    # Extract the name without extension to use for metadata
                    model_name, _ = os.path.splitext(downloaded_file_name)

                    # Make sure the directory exists; if not, create it
                    os.makedirs(final_download_path, exist_ok=True)

                    # Fetch metadata
                    self.download_metadata(model_version_id, model_type, model_name)

                    # Move the file to the final destination
                    try:
                        shutil.move(downloaded_file_path, os.path.join(final_download_path, downloaded_file_name))
                        self.main_cli.scan_directory_for_models(self.settings_cli.root_directory)
                        print("updated index")
                    except (FileNotFoundError, PermissionError) as e:
                        print(f"Error in moving the file: {e}")

                else:
                    print("No file was downloaded.")
        except requests.exceptions.RequestException as e:  # Catching all requests exceptions
            print(f"Error downloading {model_type} with version ID {model_version_id}. Will retry later.")
            print(f"Error details: {e}")
            if failed_downloads_list is not None:
                failed_downloads_list.append({'type': model_type, 'version_id': model_version_id})


    def download_model_by_hash(self, hash_value):
        # Fetch model version details by hash
        model_version_details = self.api_handler.get_model_by_hash(hash_value)
        
        if not model_version_details:
            print(f"Failed to find a model with hash {hash_value}.")
            return
        
        # Extract the model version ID
        model_version_id = model_version_details.get("id")
        if not model_version_id:
            print("Model version ID not found in the details.")
            return
        
        # Extract the model type
        model_type = model_version_details.get("model", {}).get("type", "Unknown")
        
        # Determine the final download path
        final_download_path = self.get_download_path(model_type)
        
        # Use existing method to download the model by its version ID
        self.download_model_by_id(model_version_id, final_download_path, model_type)

    def scan_and_update_metadata(self, folders=None):
        print(colored("=====================================", "yellow"))
        print(colored("🔍 Starting metadata scan...", "yellow"))
        print(colored("=====================================", "yellow"))

        # Dictionary to store filename-hash mapping
        file_hash_mapping = {}
        if folders is None:
            print(colored("\n⏳ Scanning all folders. This may take some time.", "magenta"))
            folders = list(self.type_to_path.values())

        for folder in folders:
            download_dir = os.path.join(self.default_download_dir, folder)
            print(colored(f"\n📁 Scanning folder: {download_dir}", "cyan"))

            if not os.path.exists(download_dir):
                print(colored("  🚫 Directory not found. Skipping.", "red"))
                continue 

            valid_extensions = ['.ckpt', '.pt', '.safetensors']
            needs_update = False  # Reset the flag for each folder

            for filename in os.listdir(download_dir):
                if any(filename.endswith(ext) for ext in valid_extensions):
                    base_name, ext = os.path.splitext(filename)
                    
                    # Check for accompanying metadata files
                    info_file = os.path.join(download_dir, f"{base_name}.civitai.info")
                    preview_file = os.path.join(download_dir, f"{base_name}.preview.png")
                    json_file = os.path.join(download_dir, f"{base_name}.json")

                    if not (os.path.exists(info_file) and os.path.exists(preview_file) and os.path.exists(json_file)):
                        needs_update = True  # Set the flag to True
                        print(f"\033[95mMissing metadata\033[0m for {filename}. \033[94mGenerating hash\033[0m and \033[94mfetching metadata\033[0m. 🔄")
                        
                        # Generate SHA-256 hash for the file
                        file_path = os.path.join(download_dir, filename)
                        file_hash = self.generate_sha256(file_path)

                        # Store the filename-hash mapping
                        file_hash_mapping[file_hash] = filename

                        # Download metadata using the hash
                        self.download_metadata_by_hash(file_hash, download_dir, base_name)

            if needs_update:
                print(colored(f"  🔄 Some files were missing metadata and have been updated.", "blue"))
            else:
                print(colored("  ✅ All models are up to date. No missing metadata found.", "green"))

        print(colored("\n=====================================", "yellow"))
        print(colored("✅ Metadata scan complete.", "yellow"))
        print(colored("=====================================", "yellow"))

    def generate_sha256(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def download_metadata_by_hash(self, file_hash, folder, base_name):
        # Fetch the model version details using the hash
        model_version_details = self.api_handler.get_model_by_hash(file_hash)

        if model_version_details is None:
            print(f"Failed to fetch model details for hash {file_hash}. This might be a user-trained model.")
            return

        model_type = model_version_details.get("model", {}).get("type", "Unknown")
        
        # Fetch the model_id
        model_id = model_version_details.get("modelId")
        if model_id is None:
            print("Model ID not found in the details.")
            return

        model_details = self.api_handler.get_model_by_id(model_id)
        if model_details is None:
            print("Failed to fetch model_details.")
            return

        # Use common method to save metadata
        self._save_metadata(model_version_details, model_type, base_name, model_details, folder)

    def download_metadata(self, model_version_id, model_type, model_name):
        print(f"Fetching metadata for {model_name} ({model_type}, version: {model_version_id})...")
        # Fetch the model_version_details first, then use them to get the model_id
        model_version_details = self.api_handler.get_model_version_by_id(model_version_id)
        if model_version_details is None:
            print("Failed to fetch model_version_details.")
            return

        # Now, get the model_id and use it to fetch model_details
        model_id = model_version_details.get("modelId")
        if model_id is None:
            print("Model ID not found in the details.")
            return

        model_details = self.api_handler.get_model_by_id(model_id)
        if model_details is None:
            print("Failed to fetch model_details.")
            return

        # Use common method to save metadata
        self._save_metadata(model_version_details, model_type, model_name, model_details)

    def _save_metadata(self, model_version_details, model_type, model_name, model_details, folder=None):
        print(f"Saving metadata for {model_name} ({model_type})...")
        download_folder = self.get_download_path(model_type) if folder is None else folder
        #print(f"Metadata will be saved to: {download_folder}")
        # Determine the folder based on the model type

        # Debug print statements
        #print(f"Debug: The download_folder is {download_folder}")

        # Save .civitai.info (with formatted JSON)
        info_file_path = os.path.join(download_folder, f"{model_name}.civitai.info")
        
        # More debug print statements
        #print(f"Debug: The info_file_path is {info_file_path}")

        try:
            with open(info_file_path, 'w') as f:
                json.dump(model_version_details, f, indent=4)
        except FileNotFoundError as e:
            print(f"FileNotFoundError: {e}")
            return

        # Save .json
        new_json_format = {
            "description": self.format_html_to_text(model_details.get("description", "N/A")),
            "notes": model_version_details.get("description", "N/A"),
            "sd version": self.map_sd_version(model_version_details.get("baseModel", "Other")),
            "preferred weight": 0,  # Assuming you want to default this to 0
            "extensions": {
                "Civitai_cli": {
                    "version": "0.6"
                }
            }
        }
        
        # Save the new JSON format
        json_file_path = os.path.join(download_folder, f"{model_name}.json")
        with open(json_file_path, 'w') as f:
            json.dump(new_json_format, f, indent=4)

        # Download and save .preview.png
        image_url = model_version_details["images"][0].get("url", None) if model_version_details.get("images") else None
        if image_url:
            preview_file_path = os.path.join(download_folder, f"{model_name}.preview.png")
            response = requests.get(image_url, allow_redirects=False)
            if response.status_code == 200:
                with open(preview_file_path, 'wb') as f:
                    f.write(response.content)
            else:
                print(f"Failed to download image from {image_url}.")

        print(f"Successfully downloaded and saved metadata for {model_name}.")

class ModelDisplay:
    def __init__(self, size='medium', text_only=False):
        self.size = size  # 'small', 'medium', 'large'
        self.text_only = text_only
        self.terminal_type = self._detect_terminal_type()
        self.size_mapping = self._get_size_mapping()

    def _detect_terminal_type(self):
        term = os.getenv("TERM", "")
        colorterm = os.getenv("COLORTERM", "")
        if term in ["xterm-kitty", "xterm-iterm"] and not self.text_only:
            # Supports graphics protocol
            return "image"
        elif colorterm in ["truecolor", "24bit"] and not self.text_only:
            # Supports truecolor
            return "truecolor"
        else:
            # ASCII blocks
            return "ascii"
        
    def _get_size_mapping(self):
        if self.terminal_type == "image":
            # Sizes optimized for image display
            return {'small': 10, 'medium': 40, 'large': 80}
        else:
            # Sizes optimized for ASCII block display
            return {'small': 20, 'medium': 80, 'large': 160}

    def get_display_size(self):
        return self.size_mapping.get(self.size, 40)

    @staticmethod
    def convert_size(size_kb):
        if size_kb >= 1000000:  # Greater than or equal to 1000 MB
            return f"{size_kb / 1000000:.2f} GB"
        elif size_kb >= 1000:  # Greater than or equal to 1000 KB
            return f"{size_kb / 1000:.2f} MB"
        else:
            return f"{size_kb} KB"

    @staticmethod
    def get_scan_color(status):
        if status == 'Success':
            return '\033[32m'  # Light Green
        elif status == 'Partial Success':
            return '\033[92m'  # Green
        elif status == 'Pending':
            return '\033[33m'  # Yellow
        else:
            return '\033[91m'  # Light Red

    def display_model_card(self, model, image_filter, download_status, image_filter_settings):
        nsfw_status = None
        action = image_filter_settings.get(nsfw_status, 'allow')
        model_name = model.get('name', 'N/A')
        total_length = 125  
        padding_length = (total_length - len(model_name)) // 2  
        reset_color = '\033[0m\033[49m'
        separator = f"{'.' * padding_length}\033[1m{model_name}\033[0m{'.' * (total_length - len(model_name) - padding_length)}"
        print(separator)
        print()

        # Print Basic Info
        print(f"🆔 ID: {model.get('id', 'N/A')}")
        base_url = "https://civitai.com/models/"
        model_id = model.get('id', 'N/A')
        full_url = f"{base_url}{model_id}"
        print(f"🌐 URL: \033[94m\033[4m{full_url}\033[0m")
        print(f"📛 Name: {model.get('name', 'N/A')}")
        print(f"👤 Creator: {model.get('creator', {}).get('username', 'N/A')}")
        print(f"🤖 Type: {model.get('type', 'N/A')}")

        # Print download status
        if download_status:
            print(f"📥 Download Status: {download_status}")
        model_versions = model.get('modelVersions', [])
        if model_versions:
            base_models = set(version.get('baseModel', 'N/A') for version in model_versions)
            base_models_str = ', '.join(base_models)
            files_info = model_versions[0].get('files', [{}])  # Get the first file info dictionary from the list, or an empty dict if not available
            size_kb = files_info[0].get('sizeKB', 'N/A') if files_info else 'N/A'
            if size_kb != 'N/A':
                size_kb = self.convert_size(size_kb)
            pickle_scan = files_info[0].get('pickleScanResult', 'N/A')
            virus_scan = files_info[0].get('virusScanResult', 'N/A')
            scanned_at = files_info[0].get('scannedAt', 'N/A')
            pickle_scan_color = self.get_scan_color(pickle_scan)
            virus_scan_color = self.get_scan_color(virus_scan)
        else:
            base_models_str = 'N/A'
            size_kb = 'N/A'
            pickle_scan = 'N/A'
            virus_scan = 'N/A'
            pickle_scan_color = self.get_scan_color('N/A')
            virus_scan_color = self.get_scan_color('N/A')
            scanned_at = 'N/A'

        print(f"🛠️ Base Models: {base_models_str}")
        print(f"⭐ Rating: {model.get('stats', {}).get('rating', 'N/A')}")
        print(f"🔞 NSFW: {model.get('nsfw', 'N/A')}")
        print(f"🏷️ Tags: {', '.join(model.get('tags', ['N/A']))}")
        print(f"📦 File Size: \033[1m{size_kb}\033[0m")
        print("\n-- Scans --")
        print(f"🐍 Pickle Scan: {pickle_scan_color}{pickle_scan}{reset_color}")
        print(f"🔬 Virus Scan: {virus_scan_color}{virus_scan}{reset_color}")
        print(f"🗓️ Scanned At: {scanned_at}")
        print("\n-- Description --")
        raw_description = model.get('description', '')
        if raw_description:
            stripped_description = re.sub('<.*?>', '', raw_description)
            truncated_description = (stripped_description[:200] + '...') if len(stripped_description) > 200 else stripped_description
        else:
            truncated_description = 'N/A'
        print(f"\n📝 Description: {truncated_description}\n")
        print( )
        # Safely fetch image URL
        model_versions = model.get('modelVersions', [])
        if model_versions:
            images = model_versions[0].get('images', [])
            if images:
                image_url = images[0].get('url', 'N/A')
            else:
                image_url = 'N/A'
        else:
            image_url = 'N/A'

        #print(f"Image URL: {image_url}")
        if not self.text_only:
            nsfw_warning_displayed = False  

            nsfw_status = 'None'  # Initialize to a default value

            for model_version in model.get('modelVersions', []):
                for image in model_version.get('images', []):
                    nsfw_status = image.get('nsfw', 'None')  # Get NSFW status of the image

                    action = image_filter_settings.get(nsfw_status, 'allow') 
                    
                    if action == 'block':
                        if not nsfw_warning_displayed:
                            print(f"⚠️ {nsfw_status} content is blocked")
                            nsfw_warning_displayed = True
                        continue  

                    elif action == 'blockify':
                        print(f"⚠️ {nsfw_status} content is blockified")
                 
                    # Image fetching and displaying logic
                    if image_url != 'N/A':
                        try:
                            # Fetch and save the image data
                            image_data = requests.get(image_url).content
                            image_format = imghdr.what(None, image_data)  

                            if image_format not in {"png", "jpeg", "gif"}:
                                raise Image.UnidentifiedImageError("Unsupported image format")
                            
                            elif image_format == "gif":
                                # If action is 'blockify', use the -b option in viu
                                if action == 'blockify':
                                    subprocess.run(["viu", "-b", "-f", "10", "-1", "-w", str(new_width), "-h", str(new_height), temp_file.name])
                                else:
                                    subprocess.run(["viu", "-f", "10", "-1", "-w", str(new_width), "-h", str(new_height), temp_file.name])
                                return

                            with NamedTemporaryFile(suffix=f".{image_format}", delete=True) as temp_file:
                                temp_file.write(image_data)
                                temp_file.flush()

                                with Image.open(temp_file.name) as img:
                                    width, height = img.size

                                aspect_ratio = width / height
                                new_height = self.size_mapping.get(self.size, 80)  
                                correction_factor = 1.9
                                new_width = int(new_height * aspect_ratio * correction_factor)

                                # If action is 'blockify', use the -b option in viu
                                if action == 'blockify':
                                    subprocess.run(["viu", "-b", "-w", str(new_width), "-h", str(new_height), temp_file.name])
                                else:
                                    subprocess.run(["viu", "-w", str(new_width), "-h", str(new_height), temp_file.name])

                                return  

                        except requests.RequestException:
                            print(f"🚫 Failed to fetch image from {image_url}")
                        except Image.UnidentifiedImageError:
                            print(f"🐟 Image from {image_url} not recognized")
                        except subprocess.CalledProcessError:
                            print("⚠️ Failed to run viu")
                        except Exception as e:
                            print(f"🚫 An unexpected error occurred: {str(e)}")
            # If the code reaches here, no image could be displayed
            print("⚠️ No image could be displayed")
            print(".")


    
    def display_model_version_details(self, model, image_filter_settings):
        correction_factor = 1.9
        model_name = model.get('name', 'N/A')
        total_length = 125  # Total length of the separator line
        padding_length = (total_length - len(model_name)) // 2  # Calculate padding for each side
        reset_color = '\033[0m\033[49m'
        separator = f"{'.' * padding_length}\033[1m{model_name}\033[0m{'.' * (total_length - len(model_name) - padding_length)}"
        print(separator)
        print()
        print()

        print(f"🆔 ID: {model.get('id', 'N/A')}")
        
        # Construct and print the URL
        base_url = "https://civitai.com/models/"
        model_id = model.get('id', 'N/A')
        full_url = f"{base_url}{model_id}"
        print(f"🌐 URL: \033[94m\033[4m{full_url}\033[0m")
        
        print(f"📛 Name: {model.get('name', 'N/A')}")
        print(f"👤 Creator: {model.get('creator', {}).get('username', 'N/A')}")
        print(f"🤖 Type: {model.get('type', 'N/A')}")
        # Fetch model versions to display base model information
        model_versions = model.get('modelVersions', [])
        if model_versions:
            base_models = set(version.get('baseModel', 'N/A') for version in model_versions)
            base_models_str = ', '.join(base_models)
            files_info = model_versions[0].get('files', [{}])  # Get the first file info dictionary from the list, or an empty dict if not available
            size_kb = files_info[0].get('sizeKB', 'N/A') if files_info else 'N/A'
            if size_kb != 'N/A':
                size_kb = self.convert_size(size_kb)
            pickle_scan = files_info[0].get('pickleScanResult', 'N/A')
            virus_scan = files_info[0].get('virusScanResult', 'N/A')
            scanned_at = files_info[0].get('scannedAt', 'N/A')
            pickle_scan_color = self.get_scan_color(pickle_scan)
            virus_scan_color = self.get_scan_color(virus_scan)
        else:
            base_models_str = 'N/A'
            size_kb = 'N/A'
            pickle_scan = 'N/A'
            virus_scan = 'N/A'
            pickle_scan_color = self.get_scan_color('N/A')
            virus_scan_color = self.get_scan_color('N/A')
            scanned_at = 'N/A'

        print(f"🛠️ Base Models: {base_models_str}")
        print(f"\n⭐ Rating: {model.get('stats', {}).get('rating', 'N/A')}")
        print(f"🔞 NSFW: {model.get('nsfw', 'N/A')}")
        print(f"🏷️ Tags: {model.get('tags', 'N/A')}")
        print(f"📦 File Size: {size_kb}")
        print(f"🐍 Pickle Scan: {pickle_scan_color}{pickle_scan}{reset_color}")
        print(f"🔬 Virus Scan: {virus_scan_color}{virus_scan}{reset_color}")
        print(f"🗓️ Scanned At: {scanned_at}")    

        raw_description = model.get('description', '')
        if raw_description:
            stripped_description = re.sub('<.*?>', '', raw_description)
            truncated_description = (stripped_description[:500] + '...') if len(stripped_description) > 100 else stripped_description
        else:
            truncated_description = 'N/A'
        
        print(f"\n📝 Description: {truncated_description}")
        print( )
        # Safely fetch image URL
        model_versions = model.get('modelVersions', [])
        if model_versions:
            images = model_versions[0].get('images', [])
            if images:
                image_url = images[0].get('url', 'N/A')
            else:
                image_url = 'N/A'
        else:
            image_url = 'N/A'

        #print(f"Image URL: {image_url}")
        if not self.text_only:
            nsfw_warning_displayed = False  

            for model_version in model.get('modelVersions', []):
                for image in model_version.get('images', []):
                    image_url = image.get('url', 'N/A')
                    nsfw_status = image.get('nsfw', 'None')  # Get NSFW status of the image
                    
                    action = image_filter_settings.get(nsfw_status, 'allow')
                    
                    if action == 'block':
                        if not nsfw_warning_displayed:
                            print(f"⚠️ {nsfw_status} content is blocked")
                            nsfw_warning_displayed = True
                        continue  

                    elif action == 'blockify':
                        print(f"⚠️ {nsfw_status} content is blockified")
                    
                    # Image fetching and displaying logic
                    if image_url != 'N/A':
                        try:
                            # Fetch and save the image data
                            image_data = requests.get(image_url).content
                            image_format = imghdr.what(None, image_data)  

                            if image_format not in {"png", "jpeg", "gif"}:
                                raise Image.UnidentifiedImageError("Unsupported image format")
                            
                            with NamedTemporaryFile(suffix=f".{image_format}", delete=True) as temp_file:
                                temp_file.write(image_data)
                                temp_file.flush()

                                with Image.open(temp_file.name) as img:
                                    width, height = img.size

                                aspect_ratio = width / height
                                new_height = self.size_mapping.get(self.size, 80)  
                                correction_factor = 1.9
                                new_width = int(new_height * aspect_ratio * correction_factor)

                                # If action is 'blockify', use the -b option in viu
                                if action == 'blockify':
                                    subprocess.run(["viu", "-b", "-w", str(new_width), "-h", str(new_height), temp_file.name])
                                else:
                                    subprocess.run(["viu", "-w", str(new_width), "-h", str(new_height), temp_file.name])

                                return  

                        except requests.RequestException:
                            print(f"🚫 Failed to fetch image from {image_url}")
                        except Image.UnidentifiedImageError:
                            print(f"🐟 Image from {image_url} not recognized")
                        except subprocess.CalledProcessError:
                            print("⚠️ Failed to run viu")
                        except Exception as e:
                            print(f"🚫 An unexpected error occurred: {str(e)}")
            # If the code reaches here, no image could be displayed
            print("⚠️ No image could be displayed")
            print(".")        


    def display_model_by_hash(self, model_by_hash):
        # Format and display details of a model by its hash
        print(f"Hash: {model_by_hash['hash']}")
        # ... more fields


# Initialize classes
model_display = ModelDisplay()  
api_handler = APIHandler()
settings_cli = SettingsCLI(api_handler, model_display)
downloader = Downloader(api_handler, settings_cli, None, settings_cli.root_directory)  # Temporarily pass None for main_cli
main_cli = MainCLI(model_display, settings_cli, downloader)  # Now that we have a downloader, we can create main_cli
main_cli.scan_directory_for_models(settings_cli.root_directory)
main_cli.load_model_index()
downloader.main_cli = main_cli  # Now that we have main_cli, we can set it in downloader

# Main loop
while True:
    choice = main_cli.main_menu()
    #print(f"DEBUG: User choice = {choice}")
    if choice == 'List models':
        main_cli.list_models_menu()
    elif choice == 'Fetch model by ID':
        model_id = main_cli.fetch_model_by_id()
        model = api_handler.get_model_by_id(model_id)
        if model:
            # Calculate the download status
            downloaded_versions = []  # List to store downloaded versions
            model_versions = model.get('modelVersions', [])
            for index_model in main_cli.model_index.values():
                if index_model['modelid'] == model_id:
                    for version in model_versions:
                        if index_model['modelversionid'] == version.get('id'):
                            # This is a downloaded version
                            downloaded_versions.append(version.get('name'))
            download_status = None
            if downloaded_versions:
                # If downloaded versions were found
                if len(downloaded_versions) < len(model_versions):
                    # If there are more versions available than downloaded
                    if len(downloaded_versions) == 1:
                        download_status = f"{Fore.YELLOW}⚠️ MORE VERSIONS AVAILABLE. Version '{', '.join(downloaded_versions)}' is downloaded.{Style.RESET_ALL}"
                    else:
                        download_status = f"{Fore.YELLOW}⚠️ MORE VERSIONS AVAILABLE. Versions '{', '.join(downloaded_versions)}' are downloaded.{Style.RESET_ALL}"
                else:
                    # If all versions are downloaded
                    if len(downloaded_versions) == 1:
                        download_status = f"{Fore.GREEN}✅ ALL VERSIONS DOWNLOADED. Version '{', '.join(downloaded_versions)}' is downloaded.{Style.RESET_ALL}"
                    else:
                        download_status = f"{Fore.GREEN}✅ ALL VERSIONS DOWNLOADED. Versions '{', '.join(downloaded_versions)}' are downloaded.{Style.RESET_ALL}"
            model_display.display_model_card(model, settings_cli.image_filter, download_status, image_filter_settings={})
        else:
            print(f"Could not fetch model with ID: {model_id}")
    elif choice == 'Download model by ID':
        model_id = main_cli.download_model_by_id()
        downloader.handle_model_download_by_id(model_id)
    elif choice == 'Fetch model version by ID':
        model_version_id = main_cli.fetch_model_version_by_id()
        print(f"Mock: You chose to fetch model version with ID: {model_version_id}")
    elif choice == 'Fetch model by Hash':
        hash_value = main_cli.fetch_model_by_hash()
        print(f"Mock: You chose to fetch model with hash: {hash_value}")
    elif choice == 'Scan for missing data':
        main_cli.scan_for_missing_data_menu()        
    elif choice == 'Download meta Data for existing models':
        main_cli.download_metadata_menu()
    elif choice == 'Settings':
        settings_choice = settings_cli.settings_menu()
        if settings_choice == 'API Endpoint Configuration':
            settings_cli.api_endpoint_configuration()
        elif settings_choice == 'API Key Management':
            settings_cli.api_key_management()
    elif choice == 'Resume interrupted Downloads':
        for model in main_cli.selected_models_to_download:
            main_cli.downloader.download_model_by_id(
                model['version_id'],
                main_cli.downloader.get_download_path(model['type']),
                model['type']
            )
        main_cli.selected_models_to_download.clear()
    elif choice == 'Exit':
        print("Goodbye!")
        break
