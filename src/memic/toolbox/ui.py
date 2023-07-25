import re
import sys
from pathlib import Path
from time import sleep
from warnings import filterwarnings, warn

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
import soundfile as sf
import umap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from memic.encoder.inference import plot_embedding_as_heatmap
from memic.toolbox.utterance import Utterance
from PyQt5.QtCore import QStringListModel, Qt
from PyQt5.QtWidgets import *  # noqa: F403

filterwarnings("ignore")


colormap = (
    np.array(
        [
            [0, 127, 70],
            [255, 0, 0],
            [255, 217, 38],
            [0, 135, 255],
            [165, 0, 165],
            [255, 167, 255],
            [97, 142, 151],
            [0, 255, 255],
            [255, 96, 38],
            [142, 76, 0],
            [33, 0, 127],
            [0, 0, 0],
            [183, 183, 183],
            [76, 255, 0],
        ],
        dtype=np.float64,
    )
    / 255
)

default_text = """Welcome to the toolbox! To begin, load an utterance from your datasets or record one
The synthesizer expects to generate outputs that are somewhere between 5 and 12 seconds.
To mark breaks, write a new line. Each line will be treated separately.
Then, they are joined together to make the final spectrogram. Use the vocoder to generate audio.
The vocoder generates almost in constant time, so it will be more time efficient for longer inputs like this one.
On the left you have the embedding projections. Load or record more utterances to see them.
If you have at least 2 or 3 utterances from a same speaker, a cluster should form.
Synthesized utterances are of the same color as the speaker whose voice was used, but they're represented with a cross.
"""


class UI(QDialog):
    min_umap_points = 4
    max_log_lines = 5
    max_saved_utterances = 20

    def draw_utterance(self, utterance: Utterance, which):
        self.draw_spec(utterance.spec, which)
        self.draw_embed(utterance.embed, utterance.name, which)

    def draw_embed(self, embed, name, which):
        embed_ax, _ = self.current_ax if which == "current" else self.gen_ax
        embed_ax.figure.suptitle("" if embed is None else name)

        ## Embedding
        # Clear the plot
        if len(embed_ax.images) > 0:
            embed_ax.images[0].colorbar.remove()
        embed_ax.clear()

        # Draw the embed
        if embed is not None:
            plot_embedding_as_heatmap(embed, embed_ax)
            embed_ax.set_title("embedding")
        embed_ax.set_aspect("equal", "datalim")
        embed_ax.set_xticks([])
        embed_ax.set_yticks([])
        embed_ax.figure.canvas.draw()

    def draw_spec(self, spec, which):
        _, spec_ax = self.current_ax if which == "current" else self.gen_ax

        ## Spectrogram
        # Draw the spectrogram
        spec_ax.clear()
        if spec is not None:
            spec_ax.imshow(spec, aspect="auto", interpolation="none")
            spec_ax.set_title("mel spectrogram")

        spec_ax.set_xticks([])
        spec_ax.set_yticks([])
        spec_ax.figure.canvas.draw()
        if which != "current":
            self.vocode_button.setDisabled(spec is None)

    def draw_umap_projections(self, utterances: set[Utterance]):
        self.umap_ax.clear()

        speakers = np.unique([u.speaker_name for u in utterances])
        colors = {speaker_name: colormap[i] for i, speaker_name in enumerate(speakers)}
        embeds = [u.embed for u in utterances]

        # Display a message if there aren't enough points
        if len(utterances) < self.min_umap_points:
            self.umap_ax.text(
                0.5,
                0.5,
                "Add %d more points to\ngenerate the projections" % (self.min_umap_points - len(utterances)),
                horizontalalignment="center",
                fontsize=15,
            )
            self.umap_ax.set_title("")

        # Compute the projections
        else:
            if not self.umap_hot:
                self.log("Drawing UMAP projections for the first time, this will take a few seconds.")
                self.umap_hot = True

            reducer = umap.UMAP(int(np.ceil(np.sqrt(len(embeds)))), metric="cosine")
            projections = reducer.fit_transform(embeds)

            speakers_done = set()
            for projection, utterance in zip(projections, utterances):
                color = colors[utterance.speaker_name]
                mark = "x" if "_gen_" in utterance.name else "o"
                label = None if utterance.speaker_name in speakers_done else utterance.speaker_name
                speakers_done.add(utterance.speaker_name)
                self.umap_ax.scatter(projection[0], projection[1], c=[color], marker=mark, label=label)
            self.umap_ax.legend(prop={"size": 10})

        # Draw the plot
        self.umap_ax.set_aspect("equal", "datalim")
        self.umap_ax.set_xticks([])
        self.umap_ax.set_yticks([])
        self.umap_ax.figure.canvas.draw()

    def save_audio_file(self, wav, sample_rate):
        dialog = QFileDialog()
        dialog.setDefaultSuffix(".wav")
        fpath, _ = dialog.getSaveFileName(parent=self, caption="Select a path to save the audio file", filter="Audio Files (*.flac *.wav)")
        if fpath:
            # Default format is wav
            if Path(fpath).suffix == "":
                fpath += ".wav"
            sf.write(fpath, wav, sample_rate)

    def setup_audio_devices(self, sample_rate):
        input_devices = []
        output_devices = []
        for device in sd.query_devices():
            # Check if valid input
            try:
                sd.check_input_settings(device=device["name"], samplerate=sample_rate)
                input_devices.append(device["name"])
            except:
                pass

            # Check if valid output
            try:
                sd.check_output_settings(device=device["name"], samplerate=sample_rate)
                output_devices.append(device["name"])
            except Exception as e:
                # Log a warning only if the device is not an input
                if device["name"] not in input_devices:
                    warn("Unsupported output device %s for the sample rate: %d \nError: %s" % (device["name"], sample_rate, str(e)))

        if len(input_devices) == 0:
            self.log("No audio input device detected. Recording may not work.")
            self.audio_in_device = None
        else:
            self.audio_in_device = input_devices[0]

        if len(output_devices) == 0:
            self.log("No supported output audio devices were found! Audio output may not work.")
            self.audio_out_devices_cb.addItems(["None"])
            self.audio_out_devices_cb.setDisabled(True)
        else:
            self.audio_out_devices_cb.clear()
            self.audio_out_devices_cb.addItems(output_devices)
            self.audio_out_devices_cb.currentTextChanged.connect(self.set_audio_device)

        self.set_audio_device()

    def set_audio_device(self):

        output_device = self.audio_out_devices_cb.currentText()
        if output_device == "None":
            output_device = None

        # If None, sounddevice queries portaudio
        sd.default.device = (self.audio_in_device, output_device)

    def play(self, wav, sample_rate):
        try:
            sd.stop()
            sd.play(wav, sample_rate)
        except Exception as e:
            print(e)
            self.log("Error in audio playback. Try selecting a different audio output device.")
            self.log("Your device must be connected before you start the toolbox.")

    def stop(self):
        sd.stop()

    def record_one(self, sample_rate, duration):
        self.record_button.setText("Recording...")
        self.record_button.setDisabled(True)

        self.log("Recording %d seconds of audio" % duration)
        sd.stop()
        try:
            wav = sd.rec(duration * sample_rate, sample_rate, 1)
        except Exception as e:
            print(e)
            self.log("Could not record anything. Is your recording device enabled?")
            self.log("Your device must be connected before you start the toolbox.")
            return None

        for i in np.arange(0, duration, 0.1):
            self.set_loading(i, duration)
            sleep(0.1)
        self.set_loading(duration, duration)
        sd.wait()

        self.log("Done recording.")
        self.record_button.setText("Record")
        self.record_button.setDisabled(False)

        return wav.squeeze()

    @property
    def current_dataset_name(self):
        return self.dataset_box.currentText()

    @property
    def current_speaker_name(self):
        return self.speaker_box.currentText()

    @property
    def current_utterance_name(self):
        return self.utterance_box.currentText()

    def browse_file(self):
        fpath = QFileDialog().getOpenFileName(parent=self, caption="Select an audio file", filter="Audio Files (*.mp3 *.flac *.wav *.m4a)")
        return Path(fpath[0]) if fpath[0] != "" else ""

    @staticmethod
    def repopulate_box(box, items, random=False):
        """Resets a box and adds a list of items. Pass a list of (item, data) pairs instead to join
        data to the items.
        """
        box.blockSignals(True)
        box.clear()
        for item in items:
            item = list(item) if isinstance(item, tuple) else [item]
            box.addItem(str(item[0]), *item[1:])
        if len(items) > 0:
            box.setCurrentIndex(np.random.randint(len(items)) if random else 0)
        box.setDisabled(len(items) == 0)
        box.blockSignals(False)

    def populate_browser(self, datasets_root: Path, recognized_datasets: list, level: int, random=True):
        self.datasets_root = datasets_root
        self.check_filename()

        # Select a random dataset
        if level <= 0:
            if datasets_root is not None:
                datasets = [datasets_root.joinpath(d) for d in recognized_datasets]
                datasets = [d.relative_to(datasets_root) for d in datasets if d.exists()]
                self.browser_load_button.setDisabled(len(datasets) == 0)
            if datasets_root is None or len(datasets) == 0:
                msg = "Warning: you d" + (
                    "id not pass a root directory for datasets as argument"
                    if datasets_root is None
                    else "o not have any of the recognized datasets" " in %s" % datasets_root
                )
                self.log(msg)
                msg += (
                    ".\nThe recognized datasets are:\n\t%s\nFeel free to add your own. You "
                    "can still use the toolbox by recording samples yourself." % ("\n\t".join(recognized_datasets))
                )
                print(msg, file=sys.stderr)

                self.random_utterance_button.setDisabled(True)
                self.random_speaker_button.setDisabled(True)
                self.random_dataset_button.setDisabled(True)
                self.utterance_box.setDisabled(True)
                self.speaker_box.setDisabled(True)
                self.dataset_box.setDisabled(True)
                self.browser_load_button.setDisabled(True)
                self.auto_next_checkbox.setDisabled(True)
                return
            self.repopulate_box(self.dataset_box, datasets, random)

        # Select a random speaker
        if level <= 1:
            speakers_root = datasets_root.joinpath(self.current_dataset_name)
            speaker_names = [d.stem for d in speakers_root.glob("*") if d.is_dir()]
            self.repopulate_box(self.speaker_box, speaker_names, random)

        # Select a random utterance
        if level <= 2:
            utterances_root = datasets_root.joinpath(self.current_dataset_name, self.current_speaker_name)
            utterances = []
            for extension in ["mp3", "flac", "wav", "m4a"]:
                utterances.extend(Path(utterances_root).glob("**/*.%s" % extension))
            utterances = [fpath.relative_to(utterances_root) for fpath in utterances]
            self.repopulate_box(self.utterance_box, utterances, random)

    def check_filename(self):
        username = self.user_name_input.text()
        if username == "user01" and not self.datasets_root.joinpath("user01").exists():
            other = [d for d in self.datasets_root.iterdir() if d.is_dir() and all(f.suffix == ".wav" for f in d.iterdir())]
            # sort by most recent modified time to least recent
            other.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            if len(other) > 0:
                username = other[0].name
                self.user_name_input.setText(username)
                self.user_name_input_changed()

        if (
            self.datasets_root is not None
            and re.match(rf"{username}@rec\d*", self.record_name_input.text())
            and (self.datasets_root / username).exists()
        ):
            print(list((self.datasets_root / username).iterdir()))
            n = len([1 for d in (self.datasets_root / username).iterdir() if re.match(rf"{username}@rec\d*\.wav", d.name)]) + 1
            if n < 10:
                n = f"0{n}"
            self.record_name_input.setText(f"{username}@rec{n}")

    def browser_select_next(self):
        index = (self.utterance_box.currentIndex() + 1) % len(self.utterance_box)
        self.utterance_box.setCurrentIndex(index)

    @property
    def current_encoder_fpath(self):
        return self.encoder_box.itemData(self.encoder_box.currentIndex())

    @property
    def current_synthesizer_fpath(self):
        return self.synthesizer_box.itemData(self.synthesizer_box.currentIndex())

    @property
    def current_vocoder_fpath(self):
        return self.vocoder_box.itemData(self.vocoder_box.currentIndex())

    def populate_models(self, models_dir: Path):
        # Encoder
        encoder_fpaths = list(models_dir.glob("*/encoder.pt"))
        if len(encoder_fpaths) == 0:
            raise Exception("No encoder models found in %s" % models_dir)
        self.repopulate_box(self.encoder_box, [(f.parent.name, f) for f in encoder_fpaths])

        # Synthesizer
        synthesizer_fpaths = list(models_dir.glob("*/synthesizer.pt"))
        if len(synthesizer_fpaths) == 0:
            raise Exception("No synthesizer models found in %s" % models_dir)
        self.repopulate_box(self.synthesizer_box, [(f.parent.name, f) for f in synthesizer_fpaths])

        # Vocoder
        vocoder_fpaths = list(models_dir.glob("*/vocoder.pt"))
        vocoder_items = [(f.parent.name, f) for f in vocoder_fpaths] + [("Griffin-Lim", None)]
        self.repopulate_box(self.vocoder_box, vocoder_items)

    @property
    def selected_utterance(self):
        return self.utterance_history.itemData(self.utterance_history.currentIndex())

    def register_utterance(self, utterance: Utterance):
        self.utterance_history.blockSignals(True)
        self.utterance_history.insertItem(0, utterance.name, utterance)
        self.utterance_history.setCurrentIndex(0)
        self.utterance_history.blockSignals(False)

        if len(self.utterance_history) > self.max_saved_utterances:
            self.utterance_history.removeItem(self.max_saved_utterances)

        self.play_button.setDisabled(False)
        self.generate_button.setDisabled(False)
        self.synthesize_button.setDisabled(False)

    def log(self, line, mode="newline"):
        if mode == "newline":
            self.logs.append(line)
            if len(self.logs) > self.max_log_lines:
                del self.logs[0]
        elif mode == "append":
            self.logs[-1] += line
        elif mode == "overwrite":
            self.logs[-1] = line
        log_text = "\n".join(self.logs)

        self.log_window.setText(log_text)
        self.app.processEvents()

    def set_loading(self, value, maximum=1):
        self.loading_bar.setValue(int(value * 100))
        self.loading_bar.setMaximum(maximum * 100)
        self.loading_bar.setTextVisible(value != 0)
        self.app.processEvents()

    def populate_gen_options(self, seed, trim_silences):
        if seed is not None:
            self.random_seed_checkbox.setChecked(True)
            self.seed_textbox.setText(str(seed))
            self.seed_textbox.setEnabled(True)
        else:
            self.random_seed_checkbox.setChecked(False)
            self.seed_textbox.setText(str(0))
            self.seed_textbox.setEnabled(False)

        if not trim_silences:
            self.trim_silences_checkbox.setChecked(False)
            self.trim_silences_checkbox.setDisabled(True)

    def update_seed_textbox(self):
        if self.random_seed_checkbox.isChecked():
            self.seed_textbox.setEnabled(True)
        else:
            self.seed_textbox.setEnabled(False)

    def reset_interface(self):
        self.draw_embed(None, None, "current")
        self.draw_embed(None, None, "generated")
        self.draw_spec(None, "current")
        self.draw_spec(None, "generated")
        self.draw_umap_projections(set())
        self.set_loading(0)
        self.play_button.setDisabled(True)
        self.generate_button.setDisabled(True)
        self.synthesize_button.setDisabled(True)
        self.vocode_button.setDisabled(True)
        self.replay_wav_button.setDisabled(True)
        self.export_wav_button.setDisabled(True)
        [self.log("") for _ in range(self.max_log_lines)]

    def __init__(self):
        ## Initialize the application
        self.app = QApplication(sys.argv)
        super().__init__(None)
        self.setWindowTitle("SV2TTS toolbox")

        self.datasets_root = None

        ## Main layouts
        # Root
        root_layout = QGridLayout()
        self.setLayout(root_layout)

        # Browser
        browser_layout = QGridLayout()
        root_layout.addLayout(browser_layout, 0, 0, 1, 2)

        # Generation
        gen_layout = QVBoxLayout()
        root_layout.addLayout(gen_layout, 0, 2, 1, 2)

        # Projections
        self.projections_layout = QVBoxLayout()
        root_layout.addLayout(self.projections_layout, 1, 0, 1, 1)

        # Visualizations
        vis_layout = QVBoxLayout()
        root_layout.addLayout(vis_layout, 1, 1, 1, 3)

        ## Projections
        # UMap
        fig, self.umap_ax = plt.subplots(figsize=(3, 3), facecolor="#F0F0F0")
        fig.subplots_adjust(left=0.02, bottom=0.02, right=0.98, top=0.98)
        self.projections_layout.addWidget(FigureCanvas(fig))
        self.umap_hot = False
        self.clear_button = QPushButton("Clear")
        self.projections_layout.addWidget(self.clear_button)

        ## Browser
        # Dataset, speaker and utterance selection
        self.dataset_box = QComboBox()
        self.speaker_box = QComboBox()
        self.utterance_box = QComboBox()
        self.browser_load_button = QPushButton("Load")
        self.random_dataset_button = QPushButton("Random")
        self.random_speaker_button = QPushButton("Random")
        self.random_utterance_button = QPushButton("Random")
        self.auto_next_checkbox = QCheckBox("Auto select next")
        self.auto_next_checkbox.setChecked(True)
        self.utterance_history = QComboBox()
        self.browser_browse_button = QPushButton("Browse")

        self.user_name_input = QLineEdit()
        self.user_name_input.setText("user01")
        self.user_name_input.setMaxLength(20)
        self.user_name_input.setFixedWidth(100)
        # add a change callback to the user name input
        self.user_name_input.textEdited.connect(self.user_name_input_changed)

        # add a numerical input for record duration. Make the number input default to 10 and have min of 5 and max of 50
        self.record_duration_input = QSpinBox()
        self.record_duration_input.setRange(5, 100)
        self.record_duration_input.setValue(5)

        self.record_button = QPushButton("Record")

        self.record_name_input = QLineEdit()

        self.record_name_input.setText("user01@rec01")
        self.record_name_input.setMaxLength(20)
        self.record_name_input.setFixedWidth(100)

        self.play_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.encoder_box = QComboBox()
        self.synthesizer_box = QComboBox()
        self.vocoder_box = QComboBox()
        self.audio_out_devices_cb = QComboBox()

        self.waves_cb = QComboBox()
        self.waves_cb_model = QStringListModel()
        self.waves_cb.setModel(self.waves_cb_model)
        self.waves_cb.setToolTip("Select one of the last generated waves in this section for replaying or exporting")

        self.replay_wav_button = QPushButton("Replay")
        self.replay_wav_button.setToolTip("Replay last generated vocoder")

        self.export_wav_button = QPushButton("Export")
        self.export_wav_button.setToolTip("Save last generated vocoder audio in filesystem as a wav file")
        widgets = [
            [QLabel("<b>Dataset</b>"), QLabel("<b>Speaker</b>"), QLabel("<b>Utterance</b>")],
            [self.dataset_box, self.speaker_box, self.utterance_box, self.browser_load_button],
            [self.random_dataset_button, self.random_speaker_button, self.random_utterance_button, self.auto_next_checkbox],
            [QLabel("<b>Record your voice:</b>")],
            [self.user_name_input, self.record_duration_input, self.record_button, self.record_name_input],
            [QLabel("<b>Use embedding from:</b>")],
            [self.utterance_history, self.browser_browse_button, self.play_button, self.stop_button],
            [QLabel("<b>Encoder</b>"), QLabel("<b>Synthesizer</b>"), QLabel("<b>Vocoder</b>"), QLabel("<b>Audio Output</b>")],
            [self.encoder_box, self.synthesizer_box, self.vocoder_box, self.audio_out_devices_cb],
            [QLabel("<b>Toolbox Output:</b>"), self.waves_cb, self.replay_wav_button, self.export_wav_button],
        ]
        for i, row in enumerate(widgets):
            for j, widget in enumerate(row):
                browser_layout.addWidget(widget, i, j)

        ## Embed & spectrograms
        vis_layout.addStretch()

        gridspec_kw = {"width_ratios": [1, 4]}
        fig, self.current_ax = plt.subplots(1, 2, figsize=(10, 2.25), facecolor="#F0F0F0", gridspec_kw=gridspec_kw)
        fig.subplots_adjust(left=0, bottom=0.1, right=1, top=0.8)
        vis_layout.addWidget(FigureCanvas(fig))

        fig, self.gen_ax = plt.subplots(1, 2, figsize=(10, 2.25), facecolor="#F0F0F0", gridspec_kw=gridspec_kw)
        fig.subplots_adjust(left=0, bottom=0.1, right=1, top=0.8)
        vis_layout.addWidget(FigureCanvas(fig))

        for ax in self.current_ax.tolist() + self.gen_ax.tolist():
            ax.set_facecolor("#F0F0F0")
            for side in ["top", "right", "bottom", "left"]:
                ax.spines[side].set_visible(False)

        ## Generation
        self.text_prompt = QPlainTextEdit(default_text)
        gen_layout.addWidget(self.text_prompt, stretch=1)

        self.generate_button = QPushButton("Synthesize and vocode")
        gen_layout.addWidget(self.generate_button)

        layout = QHBoxLayout()
        self.synthesize_button = QPushButton("Synthesize only")
        layout.addWidget(self.synthesize_button)
        self.vocode_button = QPushButton("Vocode only")
        layout.addWidget(self.vocode_button)
        gen_layout.addLayout(layout)

        layout_seed = QGridLayout()
        self.random_seed_checkbox = QCheckBox("Random seed:")
        self.random_seed_checkbox.setToolTip("When checked, makes the synthesizer and vocoder deterministic.")
        layout_seed.addWidget(self.random_seed_checkbox, 0, 0)
        self.seed_textbox = QLineEdit()
        self.seed_textbox.setMaximumWidth(80)
        layout_seed.addWidget(self.seed_textbox, 0, 1)
        self.trim_silences_checkbox = QCheckBox("Enhance vocoder output")
        self.trim_silences_checkbox.setToolTip(
            "When checked, trims excess silence in vocoder output." " This feature requires `webrtcvad` to be installed."
        )
        layout_seed.addWidget(self.trim_silences_checkbox, 0, 2, 1, 2)
        gen_layout.addLayout(layout_seed)

        self.loading_bar = QProgressBar()
        gen_layout.addWidget(self.loading_bar)

        self.log_window = QLabel()
        self.log_window.setAlignment(Qt.AlignBottom | Qt.AlignLeft)
        gen_layout.addWidget(self.log_window)
        self.logs = []
        gen_layout.addStretch()

        ## Set the size of the window and of the elements
        max_size = QDesktopWidget().availableGeometry(self).size() * 0.8
        self.resize(max_size)

        ## Finalize the display
        self.reset_interface()
        self.show()

    def user_name_input_changed(self):
        t = self.record_name_input.text()
        if "@" in t:
            old = t.split("@")[1]
            self.record_name_input.setText(self.user_name_input.text() + "@" + old)
        self.check_filename()

    def start(self):
        self.app.exec_()