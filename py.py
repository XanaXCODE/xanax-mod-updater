import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
import webbrowser
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import string
import shutil

def get_config_path():
    if os.name == "nt": 
        base_dir = os.getenv("APPDATA")
    else:
        base_dir = os.path.expanduser("~")
    config_dir = os.path.join(base_dir, "wannacry")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.json")

def get_default_mods_folder():
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        default_path = os.path.join(appdata, ".minecraft", "mods")
        if os.path.exists(default_path):
            return default_path
    else:
        home = os.path.expanduser("~")
        default_path = os.path.join(home, ".minecraft", "mods")
        if os.path.exists(default_path):
            return default_path
    return None

def find_mods_in_all_drives():
    if os.name != "nt":
        return None
    
    for drive in string.ascii_uppercase:
        drive_path = f"{drive}:\\"
        if not os.path.exists(drive_path):
            continue
        
        users_dir = os.path.join(drive_path, "Users")
        if not os.path.exists(users_dir):
            continue
        
        try:
            users = os.listdir(users_dir)
        except PermissionError:
            continue
        
        for user in users:
            user_dir = os.path.join(users_dir, user)
            if not os.path.isdir(user_dir):
                continue
            
            mods_path = os.path.join(user_dir, "AppData", "Roaming", ".minecraft", "mods")
            if os.path.exists(mods_path):
                return mods_path
    
    return None

def load_config():
    default_config = {
        "mod_folder": "",
        "app_key": "app_key",
        "app_secret": "app_secret",
        "access_token": "",
        "dropbox_folder": "/mods"
    }
    
    if os.path.exists(get_config_path()):
        try:
            with open(get_config_path(), "r") as f:
                loaded = json.load(f)
                default_config.update(loaded)
        except Exception as e:
            print(f"Erro ao ler configuração: {e}")
    
    if not default_config["mod_folder"]:
        default_path = get_default_mods_folder()
        if default_path:
            default_config["mod_folder"] = default_path
        else:
            found_path = find_mods_in_all_drives()
            if found_path:
                default_config["mod_folder"] = found_path
    
    return default_config

def save_config(config):
    try:
        with open(get_config_path(), "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erro ao salvar configuração: {e}")

class DropboxAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get('code', [None])[0]

        if code:
            self.server.auth_code = code
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            self.wfile.write(b"""
                <html>
                    <head>
                        <title>Authentication Success</title>
                        <style>
                            body { background-color: #3A3A3A; color: white; 
                                   font-family: Arial, sans-serif; text-align: center; 
                                   padding-top: 50px; }
                            h1 { color: #4CAF50; }
                        </style>
                    </head>
                    <body>
                        <h1>Authentication Successful!</h1>
                        <p>You can now close this window and return to the app.</p>
                    </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.end_headers()

def get_auth_code():
    server = HTTPServer(('localhost', 5896), DropboxAuthHandler)
    server.auth_code = None
    threading.Thread(target=server.handle_request, daemon=True).start()
    return server

def authenticate_dropbox():
    app_key = app_key_var.get()
    app_secret = app_secret_var.get()
    
    if not app_key or not app_secret:
        messagebox.showerror("Error", "Please fill in App Key and App Secret first")
        return

    try:
        auth_flow = DropboxOAuth2FlowNoRedirect(
            app_key,
            app_secret,
            token_access_type='offline'
        )

        auth_url = auth_flow.start()
        webbrowser.open(auth_url)

        auth_code = simpledialog.askstring("Dropbox Auth", "Please enter the authorization code from Dropbox:")
        if not auth_code:
            return

        oauth_result = auth_flow.finish(auth_code)
        access_token = oauth_result.access_token
        
        config = load_config()
        config.update({
            "app_key": app_key,
            "app_secret": app_secret,
            "access_token": access_token
        })
        save_config(config)
        
        messagebox.showinfo("Success", "Successfully authenticated! Access token saved.")
        access_token_var.set("••••••••••••••••••••••••••••••")
    except Exception as e:
        messagebox.showerror("Error", f"Authentication failed: {str(e)}")

def select_mod_folder():
    folder = filedialog.askdirectory(title="Select Minecraft Mods Folder")
    if folder:
        config = load_config()
        config["mod_folder"] = folder
        save_config(config)
        mod_folder_var.set(folder)
    return folder

def sync_mods():
    config = load_config()
    access_token = config.get("access_token")
    mod_folder = mod_folder_var.get()
    dropbox_folder = dropbox_folder_var.get()
    
    if not access_token:
        messagebox.showerror("Error", "Please authenticate with Dropbox first")
        return

    if not mod_folder or not os.path.isdir(mod_folder):
        messagebox.showwarning("Warning", "Please select a valid mods folder")
        return

    try:
        dbx = dropbox.Dropbox(access_token)
        result = dbx.files_list_folder(dropbox_folder)
        dropbox_files = {entry.name: entry.path_lower for entry in result.entries if isinstance(entry, dropbox.files.FileMetadata)}

        local_files = [f for f in os.listdir(mod_folder) if f.endswith(".jar")]
        files_to_download = [f for f in dropbox_files if f not in local_files]
        files_to_remove = [f for f in local_files if f not in dropbox_files]
        total_operations = len(files_to_download) + len(files_to_remove)

        if total_operations == 0:
            messagebox.showinfo("Info", "All mods are up to date!")
            return

        progress_var.set(0)
        progress_bar["maximum"] = total_operations
        operations_completed = 0

        for filename, path in dropbox_files.items():
            if filename in files_to_download:
                local_path = os.path.join(mod_folder, filename)
                try:
                    metadata, res = dbx.files_download(path)
                    with open(local_path, "wb") as f:
                        f.write(res.content)
                    operations_completed += 1
                    progress_var.set(operations_completed)
                    update_progress(operations_completed, total_operations)
                except Exception as e:
                    print(f"Error downloading {filename}: {e}")

        for local_file in files_to_remove:
            try:
                os.remove(os.path.join(mod_folder, local_file))
                operations_completed += 1
                progress_var.set(operations_completed)
                update_progress(operations_completed, total_operations)
            except Exception as e:
                print(f"Error removing {local_file}: {e}")

        messagebox.showinfo("Success", "Sync completed successfully!")
    except dropbox.exceptions.AuthError:
        messagebox.showerror("Error", "Invalid or expired access token. Please reauthenticate.")
    except Exception as e:
        messagebox.showerror("Error", f"Sync failed:\n{str(e)}")

def update_progress(completed, total):
    percentage = (completed / total) * 100
    progress_label.config(text=f"Progress: {completed}/{total} ({percentage:.1f}%)")
    app.update_idletasks()

def show_token():
    config = load_config()
    if config.get("access_token"):
        messagebox.showinfo("Access Token", f"Your current access token:\n\n{config['access_token']}")
    else:
        messagebox.showinfo("Access Token", "No access token configured.")


app = tk.Tk()
app.title("titio xanax apresenta: mod updater")
app.configure(bg="#3A3A3A")


config = load_config()

auth_frame = tk.LabelFrame(app, text="Primeiro passo", padx=10, pady=10, bg="#3A3A3A", fg="white")
auth_frame.pack(padx=10, pady=5, fill="x")


app_key_var = tk.StringVar(value=config.get("app_key", ""))


app_secret_var = tk.StringVar(value=config.get("app_secret", ""))

tk.Button(auth_frame, text="Authenticate with Dropbox", command=authenticate_dropbox, bg="blue", fg="white").grid(row=2, column=0, columnspan=2, pady=5)


access_token_var = tk.StringVar(value="••••••••••••••••••••••••••••••" if config.get("access_token") else "")


config_frame = tk.LabelFrame(app, text="Segundo passo", padx=10, pady=10, bg="#3A3A3A", fg="white")
config_frame.pack(padx=10, pady=5, fill="x")

tk.Label(config_frame, text="Minecraft Mods Folder:", bg="#3A3A3A", fg="white").grid(row=0, column=0, sticky="w")
mod_folder_var = tk.StringVar(value=config.get("mod_folder", ""))
tk.Entry(config_frame, textvariable=mod_folder_var, width=40, bg="#505050", fg="white").grid(row=1, column=0, padx=5, pady=2)
tk.Button(config_frame, text="Select Folder", command=select_mod_folder, bg="#505050", fg="white").grid(row=1, column=1, padx=5, pady=2)

dropbox_folder_var = tk.StringVar(value=config.get("dropbox_folder", "/mods"))

progress_frame = tk.Frame(app, bg="#3A3A3A")
progress_frame.pack(padx=10, pady=10, fill="x")

progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
progress_bar.pack(fill="x", pady=5)

progress_label = tk.Label(progress_frame, text="Progress: 0/0 (0%)", bg="#3A3A3A", fg="white")
progress_label.pack()


sync_button = tk.Button(app, text="Update", command=sync_mods, bg="green", fg="white", font=("Arial", 12, "bold"))
sync_button.pack(pady=10)

app.mainloop()