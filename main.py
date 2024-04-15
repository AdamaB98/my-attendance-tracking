import cv2
import pickle
import os
import face_recognition
import numpy as np
from datetime import datetime, timedelta
import csv
import firebase_admin
from firebase_admin import credentials, db
import time
import streamlit as st
import uuid
from dotenv import load_dotenv, dotenv_values 
os.environ['PYVISTA_OFF_SCREEN'] = 'true'

load_dotenv()

st.set_page_config(layout="centered", page_title="Attendance Tracking")


st.markdown(
    """
    <style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #808080;
    }
    # .stApp {
    #     max-width: 1200px;
    #     margin: 0 auto;
    # }
    .stMarkdown h1, .stMarkdown h2 {
        color: #23558A}
        </style>
        """,
        unsafe_allow_html=True,
)

# Load Firebase credentials
cred = credentials.Certificate("serviceAccountKey.json")

# Check if Firebase app is already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "databaseURL": os.getenv('DATABASE_URL'),
        "storageBucket": os.getenv('STORAGE_BUCKET')
    })

# Initialize session state variables
if "modeType" not in st.session_state:
    st.session_state.modeType = 0

# Initialize start_time
start_time = datetime.now()

# Function to display student info
def display_student_info(student_id):
    ref = db.reference(f'Students/{student_id}')
    student_info = ref.get()
    if student_info:
        return student_info['firstname'], student_info['lastname']
    return None, None

# Function to save attendance to CSV
def save_to_csv(student_name):
    with open('attendance.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([student_name, 'present', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# Load encoded data
with open("Encodefile.p", "rb") as file:
    encodeListKnownWithIDs = pickle.load(file)
    encodeListKnown, studentIDs = encodeListKnownWithIDs

st.title("Real-time Attendance Tracking")
mode_display = st.empty()
mode_display.write("Mode Type: Active")
webcam = cv2.VideoCapture(0)
webcam.set(3, 640)
webcam.set(4, 480)
temp = st.empty()

# Keep track of the most recent recognized face and whether the confirmation box has been displayed
recognized_face = None
confirmation_displayed = False
start_time_recognition = None

 
while True:
    successful_frame_read, frame = webcam.read()
    if not successful_frame_read:
        st.write("Failed to capture frame")
        break

    # Convert frame to RGB format
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Detect faces in the image
    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
        # Compare face encoding with known encodings
        matches = face_recognition.compare_faces(encodeListKnown, face_encoding, tolerance=0.5)
        if True in matches:
            # Get the index of the matched face
            match_index = matches.index(True)
            student_id = studentIDs[match_index]
            firstname, lastname = display_student_info(student_id)
            if firstname and lastname:
                # Draw rectangle around the face and display student info
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, f"{lastname} {student_id}", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 255, 0), 2)

                # Store the most recent recognized face
                recognized_face = (student_id, firstname, lastname)
                # Restart the timer for recognition
                start_time_recognition = datetime.now()
        else:
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
            cv2.putText(frame, "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # Check if the confirmation box needs to be displayed
    if st.session_state.modeType == 0 and recognized_face and not confirmation_displayed:
        student_id, firstname, lastname = recognized_face
        if st.session_state.get(f"{firstname} {lastname} {student_id}", False):
            # If the confirmation box has already been displayed, get the current confirmation key
            if st.session_state[f"{firstname} {lastname} {student_id}"] == "No":
                # Generate a new confirmation key if the confirmation value is "No"
                confirmation_key = str(uuid.uuid4())
                st.session_state[f"{firstname} {lastname} {student_id}"] = confirmation_key
            else:
                # Use the existing confirmation key if the confirmation value is "Yes"
                confirmation_key = st.session_state[f"{firstname} {lastname} {student_id}"]
        else:
            # Generate a new confirmation key if the confirmation box has not been displayed
            confirmation_key = str(uuid.uuid4())
            st.session_state[f"{firstname} {lastname} {student_id}"] = confirmation_key
        confirmation = st.selectbox(f"Are you {firstname} {lastname}?", ("Yes", "No"), key=confirmation_key, 
                                    index=None, placeholder="Select")
        if confirmation == 'Yes':
            student_name = f"{firstname} {lastname}"
            save_to_csv(student_name)
            st.session_state.modeType = 1  # Marked
            mode_display.write("Mode Type: Marked")
            st.session_state.marked_time = datetime.now()
            # Remove the confirmation key to prevent the user from confirming again for the same face
            st.session_state[f"{firstname} {lastname} {student_id}"] = "Yes"
        elif start_time_recognition is not None and datetime.now() - start_time_recognition > timedelta(seconds=30):
            # No face has been recognized for 30 seconds, so reset recognized_face and print message
            recognized_face = None
            st.write("No face has been recognized for 30 seconds.")
        # Continue with the loop if the confirmation is "No" and the time from start_time_recognition is not yet 30 seconds
        elif confirmation_displayed == False:
            confirmation_displayed = True
        elif confirmation == 'No':
            # Generate a new confirmation key if the confirmation value is "No"
            confirmation_key = str(uuid.uuid4())
            st.session_state[f"{firstname} {lastname} {student_id}"] = confirmation_key
            continue
        # confirmation_displayed = True
    # else:
    #                 # Draw rectangle around the face and label as "Unknown"
    #     cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
    #     cv2.putText(frame, "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    # Reset the flag when a new face is detected
    if not confirmation_displayed and recognized_face:
        confirmation_displayed = False

    # Check if program should end due to already marked mode
    if st.session_state.modeType == 1 and datetime.now() - st.session_state.marked_time >= timedelta(seconds=10):
        st.session_state.modeType = 2  # Change mode to "Already Marked"
        mode_display.write("Mode Type: Already Marked")
        st.session_state.already_marked_time = datetime.now()  # Record time when mode changes to "Already Marked"

    # Check if program should end
    if st.session_state.modeType == 2 and datetime.now() - st.session_state.already_marked_time >= timedelta(seconds=5):
        # Calculate total time and time taken to mark
        total_time = datetime.now() - start_time
        time_taken_to_mark = st.session_state.marked_time - start_time

        # Display time taken to mark and total time
        st.write(f"Time taken to mark: {time_taken_to_mark}")
        st.write(f"Total time: {total_time}")

        # End the program
        break

    # Display mode status on the video frame
    temp.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), channels="RGB", use_column_width=True)

# Provide a download button for the CSV file
csv_download_button = st.download_button(
    label="Download Attendance CSV",
    data=open('attendance.csv', 'rb'),
    file_name='attendance.csv',
    mime='text/csv'
)
if csv_download_button:
    st.write("Download complete!")
