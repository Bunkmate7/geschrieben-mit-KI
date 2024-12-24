import neurosky_mindwave as mindwave
import keyboard
import pyautogui
import time
import logging
import tkinter as tk
from tkinter import ttk, Scale, StringVar
import pygame
from sklearn.ensemble import RandomForestClassifier
import numpy as np

# Logger konfigurieren
logging.basicConfig(filename='neurosky_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

# Sound-Initialisierung
pygame.mixer.init()
sound_options = ['click.wav', 'alert.wav']
click_sound = pygame.mixer.Sound(sound_options[0])
alert_sound = pygame.mixer.Sound(sound_options[1])

# Verbindung zum NeuroSky-Headset herstellen
headset = mindwave.Headset('COM3')  # COM-Port anpassen, falls nötig
headset.connect()

# Initialisierung der Variablen
attention, meditation, blink_strength = 0, 0, 0
delta, theta, alpha, beta, gamma = 0, 0, 0, 0, 0
data = {"attention": [], "meditation": [], "delta": [], "theta": [], "alpha": [], "beta": [], "gamma": []}
collecting_data = True
auto_adjust = True
X = []
y = []

# Initialisiere den Klassifikator
clf = RandomForestClassifier()

# GUI erstellen
root = tk.Tk()
root.title("NeuroSky Dashboard")

mainframe = ttk.Frame(root, padding="10 10 12 12")
mainframe.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))

# Labels für Gehirnwellensignale
labels = ["Attention", "Meditation", "Blink Strength", "Delta", "Theta", "Alpha", "Beta", "Gamma"]
variables = {label: StringVar() for label in labels}

for i, label in enumerate(labels, 1):
    ttk.Label(mainframe, text=f"{label}:").grid(column=1, row=i, sticky=tk.W)
    ttk.Label(mainframe, textvariable=variables[label]).grid(column=2, row=i, sticky=(tk.W, tk.E))

for child in mainframe.winfo_children():
    child.grid_configure(padx=5, pady=5)

# Schaltflächen für Aktionen
def perform_space():
    keyboard.press_and_release('space')
    click_sound.play()
    logging.info("Leertaste gedrückt")

def perform_enter():
    keyboard.press_and_release('enter')
    click_sound.play()
    logging.info("Enter-Taste gedrückt")

def perform_left_click():
    pyautogui.click()
    click_sound.play()
    logging.info("Linksklick ausgeführt")

def perform_right_click():
    pyautogui.click(button='right')
    click_sound.play()
    logging.info("Rechtsklick ausgeführt")

def save_data():
    with open('neurosky_data.txt', 'w') as f:
        for key, values in data.items():
            f.write(f"{key}: {values}\n")
    logging.info("Daten gespeichert")

def start_collection():
    global collecting_data
    collecting_data = True
    alert_sound.play()
    logging.info("Datenerfassung gestartet")

def stop_collection():
    global collecting_data
    collecting_data = False
    alert_sound.play()
    logging.info("Datenerfassung gestoppt")

def reset_data():
    global data, X, y
    data = {key: [] for key in data.keys()}
    X, y = [], []
    alert_sound.play()
    logging.info("Daten zurückgesetzt")

# Funktionen zur Datenerfassung und Modelltraining
def collect_data(label):
    global X, y
    features = [attention, meditation, blink_strength, delta, theta, alpha, beta, gamma]
    X.append(features)
    y.append(label)
    logging.info(f"Daten gesammelt: {features} -> {label}")

def train_model():
    global clf, X, y
    if len(X) > 10:
        clf.fit(X, y)
        logging.info("Modell trainiert")
    else:
        logging.warning("Nicht genügend Daten zum Trainieren")

def predict_action():
    global clf
    if len(X) > 10:
        features = [attention, meditation, blink_strength, delta, theta, alpha, beta, gamma]
        prediction = clf.predict([features])
        logging.info(f"Vorhersage: {prediction[0]}")
        execute_action(prediction[0])
    else:
        logging.warning("Modell ist nicht trainiert")

def execute_action(action):
    if action == 'space':
        perform_space()
    elif action == 'enter':
        perform_enter()
    elif action == 'left_click':
        perform_left_click()
    elif action == 'right_click':
        perform_right_click()

# Automatische Anpassung der Schwellenwerte
def adjust_thresholds():
    if len(data["attention"]) > 100:
        attention_avg = np.mean(data["attention"])
        meditation_avg = np.mean(data["meditation"])
        delta_avg = np.mean(data["delta"])
        theta_avg = np.mean(data["theta"])
        alpha_avg = np.mean(data["alpha"])
        beta_avg = np.mean(data["beta"])
        gamma_avg = np.mean(data["gamma"])

        attention_slider.set(attention_avg)
        meditation_slider.set(meditation_avg)
        delta_slider.set(delta_avg)
        theta_slider.set(theta_avg)
        alpha_slider.set(alpha_avg)
        beta_slider.set(beta_avg)
        gamma_slider.set(gamma_avg)

        logging.info(f"Automatische Schwellenwerte angepasst: Aufmerksamkeit={attention_avg}, Meditation={meditation_avg}, Delta={delta_avg}, Theta={theta_avg}, Alpha={alpha_avg}, Beta={beta_avg}, Gamma={gamma_avg}")

# GUI-Elemente für Datenerfassung und Modelltraining
ttk.Button(mainframe, text="Space", command=lambda: collect_data('space')).grid(column=6, row=1, sticky=tk.W)
ttk.Button(mainframe, text="Enter", command=lambda: collect_data('enter')).grid(column=6, row=2, sticky=tk.W)
ttk.Button(mainframe, text="Linksklick", command=lambda: collect_data('left_click')).grid(column=6, row=3, sticky=tk.W)
ttk.Button(mainframe, text="Rechtsklick", command=lambda: collect_data('right_click')).grid(column=6, row=4, sticky=tk.W)
ttk.Button(mainframe, text="Modell trainieren", command=train_model).grid(column=6, row=5, sticky=tk.W)
ttk.Button(mainframe, text="Aktion vorhersagen", command=predict_action).grid(column=6, row=6, sticky=tk.W)
ttk.Button(mainframe, text="Schwellenwerte anpassen", command=adjust_thresholds).grid(column=6, row=7, sticky=tk.W)

# Sliders für Schwellenwerte
def update_thresholds():
    global attention_threshold, meditation_threshold, delta_threshold, theta_threshold, alpha_threshold, beta_threshold, gamma_threshold
    attention_threshold = attention_slider.get()
    meditation_threshold = meditation_slider.get()
    delta_threshold = delta_slider.get()
    theta_threshold = theta_slider.get()
    alpha_threshold = alpha_slider.get()
    beta_threshold = beta_slider.get()
    gamma_threshold = gamma_slider.get()
    logging.info(f"Schwellenwerte aktualisiert: Aufmerksamkeit={attention_threshold}, Meditation={meditation_threshold}, Delta={delta_threshold}, Theta={theta_threshold}, Alpha={alpha_threshold}, Beta={beta_threshold}, Gamma={gamma_threshold}")

ttk.Label(mainframe, text="Aufmerksamkeitsschwelle:").grid(column=4, row=1, sticky=tk.W)
attention_slider = Scale(mainframe, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda x: update_thresholds())
attention_slider.set(70)
attention_slider.grid(column=5, row=1, sticky=(tk.W, tk.E))

ttk.Label(mainframe, text="Meditationsschwelle:").grid(column=4, row=2, sticky=tk.W)
meditation_slider = Scale(mainframe, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda x: update_thresholds())
meditation_slider.set(70)
meditation_slider.grid(column=5, row=2, sticky=(tk.W, tk.E))

ttk.Label(mainframe, text="Delta-Schwelle:").grid(column=4, row=3, sticky=tk.W)
delta_slider = Scale(mainframe, from_=0, to=1000000, orient=tk.HORIZONTAL, command=lambda x: update_thresholds())
delta_slider.set(500000)
delta_slider.grid(column=5, row=3, sticky=(tk.W, tk.E))

ttk.Label(mainframe, text="Theta-Schwelle:").grid(column=4, row=4, sticky=tk.W)
theta_slider = Scale(mainframe, from_=0, to=1000000, orient=tk.HORIZONTAL, command=lambda x: update_thresholds())
theta_slider.set(500000)
theta_slider.grid(column=5, row=4, sticky=(tk.W, tk.E))

# Aktivieren der automatischen Anpassung
auto_adjust_var = tk.BooleanVar(value=True)
ttk.Checkbutton(mainframe, text="Automatische Anpassung aktivieren", variable=auto_adjust_var, command=adjust_thresholds).grid(column=6, row=8, sticky=tk.W)

# Starten
