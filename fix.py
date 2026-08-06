import sys
import os

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
skip_main_loop = False

for i, line in enumerate(lines):
    if line.startswith('import concurrent.futures'):
        continue
        
    if "def traiter_une_video_wrapper(args):" in line:
        skip = True
        continue
        
    if skip and "def main():" in line:
        skip = False
        # continue processing normally
        
    if skip:
        continue

    if "args_list = []" in line and "    args_list = []\n" == line:
        # We start skipping the multiprocessing loop
        skip_main_loop = True
        new_lines.append("""    for idx, video_data in enumerate(groupes, start=1):
        # --- DEBUT TIMER ---
        start_time = time.time()
        # -------------------

        groupe = video_data['paths']
        video_title = video_data['title']
        clip_durations = video_data.get('durations', {})
        
        print(f"\\n===== Génération de la vidéo {idx}/{len(groupes)} (≥ {TARGET_SECONDS}s) =====")
        first_clip = groupe[0]
        temp_frame = first_clip.replace(".mp4", f"_frame_{idx}.jpg")
        if not extraire_image(first_clip, temp_frame):
            print("❌ Erreur extraction image.")
            continue

        crop_params = None  # Superposition webcam désactivée
        output_final = os.path.join(output_folder, f"tiktok_final_{idx}.mp4")
        
        montage_tiktok(groupe, crop_params, output_final, clip_durations=clip_durations)

        # Génération de la description avec Groq
        generated_caption = generate_metadata(SEARCH_QUERY, video_title)

        # Envoi Telegram
        if SEND_TELEGRAM:
            client_tg_id = TELEGRAM_CHAT_ID_OVERRIDE

            client_info = None
            if client_tg_id:
                try:
                    from license_manager import validate_license, consume_license
                    lic_data = validate_license(_CURRENT_LICENSE_KEY) if _CURRENT_LICENSE_KEY else {}
                    client_info = {
                        'name':         lic_data.get('client_name', 'Client'),
                        'plan_label':   lic_data.get('plan_label', '?'),
                        'usage_today':  lic_data.get('usage_today', '?'),
                        'videos_per_day': lic_data.get('videos_per_day', '?'),
                        'telegram_chat_id': client_tg_id,
                        'license_key':  _CURRENT_LICENSE_KEY,
                    }
                    consume_license(_CURRENT_LICENSE_KEY)
                except Exception:
                    client_info = {'telegram_chat_id': client_tg_id, 'name': 'Client', 'plan_label': '?',
                                   'usage_today': '?', 'videos_per_day': '?', 'license_key': ''}

            send_telegram_video(output_final, generated_caption, client_info=client_info)
        else:
            print("📧 Envoi Telegram désactivé (SEND_TELEGRAM = False)")

        # Si Auto-post activé
        if AUTO_POST and not YOUTUBE_MODE:
            remote_filename = os.path.basename(output_final)
            if upload_to_ftp(output_final, remote_filename):
                if publish_to_late_api(remote_filename, generated_caption):
                    delete_file_from_ftp(remote_filename)
        elif YOUTUBE_MODE:
            print(f"▶️ Mode YouTube Short : pas de post TikTok.")
            print(f"💾 Vidéo YouTube Short sauvegardée : {output_final}")
        else:
            print(f"💾 Vidéo sauvegardée localement uniquement : {output_final}")
            print("🚫 Auto-post désactivé (AUTO_POST = False).")

        # 🧹 Nettoyage
        print(f"🧹 Suppression des {len(groupe)} clips sources...")
        for clip_path in groupe:
            try:
                os.remove(clip_path)
                print(f"   🗑️ Supprimé : {clip_path}")
            except Exception as e:
                print(f"   ❌ Erreur suppression {clip_path} : {e}")

        if os.path.exists(temp_frame):
            try:
                os.remove(temp_frame)
            except:
                pass
        
        # --- FIN TIMER & SAUVEGARDE ---
        end_time = time.time()
        duration = end_time - start_time
        final_vid_duration, _, _ = get_video_info(output_final)
        ai_title = generated_caption.split('\\n')[0].strip() if generated_caption else video_title
        
        save_creation_log(SEARCH_QUERY, ai_title, os.path.basename(output_final), duration, final_vid_duration)
\n""")
        continue
        
    if skip_main_loop and "def executer_pipeline(config_user):" in line:
        skip_main_loop = False
        
    if skip_main_loop and "    # --- MULTI-PROCESSING OVERHAUL ---" in line:
        new_lines.pop() # remove this line too
        
    if not skip and not skip_main_loop:
        new_lines.append(line)

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
