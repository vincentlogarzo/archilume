"""
Matplotlib Polygon Annotation Tool for Floor Plans
Allows interactive polygon drawing with vertex editing and persistence
"""

import matplotlib.pyplot as plt
from matplotlib.widgets import PolygonSelector, TextBox, Button
from matplotlib.patches import Polygon
import numpy as np
import json
from pathlib import Path
from tkinter import Tk, filedialog
import cv2


class PolygonAnnotator:
    def __init__(self, image_path):
        self.image_path = Path(image_path)
        self.image = cv2.imread(str(image_path))
        self.image_rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)

        # Storage for polygons
        self.polygons = []
        self.polygon_patches = []  # Store patch references for selection
        self.polygon_labels = []   # Store label text references
        self.current_polygon_vertices = []
        self.selected_polygon_idx = None  # Currently selected polygon index

        # Zoom state
        self.zoom_scale = 1.0
        self.original_xlim = None
        self.original_ylim = None

        # Setup matplotlib figure with side panel
        self.fig = plt.figure(figsize=(18, 10))

        # Main image axes (left side, takes 75% width)
        self.ax = self.fig.add_axes([0.02, 0.05, 0.68, 0.90])
        self.ax.imshow(self.image_rgb)
        self.ax.set_title(f'Polygon Annotator - {self.image_path.name}')

        # Store original view limits for zoom reset
        self.original_xlim = self.ax.get_xlim()
        self.original_ylim = self.ax.get_ylim()

        # Side panel area (right side)
        self._setup_side_panel()

        # Initialize PolygonSelector
        self.selector = PolygonSelector(
            self.ax,
            self.on_polygon_select,
            useblit=True,
            props=dict(color='cyan', linestyle='-', linewidth=2, alpha=0.5),
            handle_props=dict(markersize=8, markerfacecolor='red', markeredgecolor='white')
        )

        # Connect event handlers
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)

        # Load existing annotations if available
        self.load_annotations()
        self._update_polygon_list()

    def _setup_side_panel(self):
        """Create the side panel with input fields and buttons"""
        panel_left = 0.72
        panel_width = 0.26

        # Instructions text
        ax_instructions = self.fig.add_axes([panel_left, 0.88, panel_width, 0.08])
        ax_instructions.axis('off')
        ax_instructions.text(0, 0.9, "INSTRUCTIONS", fontsize=11, fontweight='bold')
        ax_instructions.text(0, 0.55, "1. Click to draw polygon vertices", fontsize=9)
        ax_instructions.text(0, 0.25, "2. Scroll to zoom, right-click to select", fontsize=9)
        ax_instructions.text(0, -0.05, "3. Enter label below, click Save", fontsize=9)

        # Label input
        ax_label_text = self.fig.add_axes([panel_left, 0.82, panel_width, 0.04])
        ax_label_text.axis('off')
        ax_label_text.text(0, 0.5, "Polygon Label:", fontsize=10, fontweight='bold')

        ax_label = self.fig.add_axes([panel_left, 0.77, panel_width, 0.05])
        self.label_textbox = TextBox(ax_label, '', initial='')

        # Room type input
        ax_room_text = self.fig.add_axes([panel_left, 0.71, panel_width, 0.04])
        ax_room_text.axis('off')
        ax_room_text.text(0, 0.5, "Room Type (optional):", fontsize=10, fontweight='bold')

        ax_room = self.fig.add_axes([panel_left, 0.66, panel_width, 0.05])
        self.room_textbox = TextBox(ax_room, '', initial='')

        # Status display
        ax_status = self.fig.add_axes([panel_left, 0.58, panel_width, 0.06])
        ax_status.axis('off')
        self.status_text = ax_status.text(0, 0.5, "Status: Ready to draw", fontsize=9,
                                          color='blue', style='italic')

        # Buttons row 1
        ax_save = self.fig.add_axes([panel_left, 0.51, panel_width * 0.48, 0.05])
        self.btn_save = Button(ax_save, 'Save Polygon')
        self.btn_save.on_clicked(self._on_save_click)

        ax_clear = self.fig.add_axes([panel_left + panel_width * 0.52, 0.51, panel_width * 0.48, 0.05])
        self.btn_clear = Button(ax_clear, 'Clear Current')
        self.btn_clear.on_clicked(self._on_clear_click)

        # Buttons row 2
        ax_export = self.fig.add_axes([panel_left, 0.44, panel_width * 0.48, 0.05])
        self.btn_export = Button(ax_export, 'Export JSON')
        self.btn_export.on_clicked(self._on_export_click)

        ax_delete = self.fig.add_axes([panel_left + panel_width * 0.52, 0.44, panel_width * 0.48, 0.05])
        self.btn_delete = Button(ax_delete, 'Delete Selected')
        self.btn_delete.on_clicked(self._on_delete_click)

        # Buttons row 3
        ax_reset_zoom = self.fig.add_axes([panel_left, 0.37, panel_width * 0.48, 0.05])
        self.btn_reset_zoom = Button(ax_reset_zoom, 'Reset Zoom')
        self.btn_reset_zoom.on_clicked(self._on_reset_zoom_click)

        ax_quit = self.fig.add_axes([panel_left + panel_width * 0.52, 0.37, panel_width * 0.48, 0.05])
        self.btn_quit = Button(ax_quit, 'Quit')
        self.btn_quit.on_clicked(self._on_quit_click)

        # Saved polygons list header
        ax_list_header = self.fig.add_axes([panel_left, 0.30, panel_width, 0.05])
        ax_list_header.axis('off')
        ax_list_header.text(0, 0.5, "SAVED POLYGONS (click to select):", fontsize=10, fontweight='bold')

        # Saved polygons list area
        self.ax_list = self.fig.add_axes([panel_left, 0.05, panel_width, 0.24])
        self.ax_list.axis('off')

    def on_scroll(self, event):
        """Handle scroll wheel for zooming"""
        if event.inaxes != self.ax:
            return

        # Zoom factor
        base_scale = 1.2
        if event.button == 'up':
            scale_factor = 1 / base_scale
        elif event.button == 'down':
            scale_factor = base_scale
        else:
            return

        # Get current view limits
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()

        # Get mouse position in data coordinates
        xdata = event.xdata
        ydata = event.ydata

        # Calculate new limits centered on mouse position
        new_width = (xlim[1] - xlim[0]) * scale_factor
        new_height = (ylim[1] - ylim[0]) * scale_factor

        # Compute relative position of mouse in current view
        relx = (xdata - xlim[0]) / (xlim[1] - xlim[0])
        rely = (ydata - ylim[0]) / (ylim[1] - ylim[0])

        # Set new limits
        self.ax.set_xlim([xdata - new_width * relx, xdata + new_width * (1 - relx)])
        self.ax.set_ylim([ydata - new_height * rely, ydata + new_height * (1 - rely)])

        self.fig.canvas.draw_idle()

    def on_click(self, event):
        """Handle mouse clicks for polygon selection"""
        if event.inaxes != self.ax:
            return

        # Right-click to select existing polygon
        if event.button == 3:  # Right mouse button
            self._select_polygon_at(event.xdata, event.ydata)

    def _select_polygon_at(self, x, y):
        """Select a polygon that contains the given point"""
        from matplotlib.path import Path as MplPath

        for i, poly_data in enumerate(self.polygons):
            vertices = np.array(poly_data['vertices'])
            path = MplPath(vertices)
            if path.contains_point((x, y)):
                self._select_polygon(i)
                return

        # No polygon found at click location
        self._deselect_polygon()

    def _select_polygon(self, idx):
        """Select a polygon by index"""
        # Deselect previous
        if self.selected_polygon_idx is not None and self.selected_polygon_idx < len(self.polygon_patches):
            old_patch = self.polygon_patches[self.selected_polygon_idx]
            old_patch.set_edgecolor('green')
            old_patch.set_linewidth(2)

        self.selected_polygon_idx = idx

        # Highlight selected polygon
        if idx < len(self.polygon_patches):
            patch = self.polygon_patches[idx]
            patch.set_edgecolor('yellow')
            patch.set_linewidth(4)

        # Load polygon data into text boxes for editing
        poly_data = self.polygons[idx]
        self.label_textbox.set_val(poly_data.get('label', ''))
        self.room_textbox.set_val(poly_data.get('room_type', ''))

        self._update_status(f"Selected: {poly_data.get('label', 'unnamed')}", 'orange')
        self._update_polygon_list()
        self.fig.canvas.draw_idle()

    def _deselect_polygon(self):
        """Deselect any selected polygon"""
        if self.selected_polygon_idx is not None and self.selected_polygon_idx < len(self.polygon_patches):
            patch = self.polygon_patches[self.selected_polygon_idx]
            patch.set_edgecolor('green')
            patch.set_linewidth(2)

        self.selected_polygon_idx = None
        self.label_textbox.set_val('')
        self.room_textbox.set_val('')
        self._update_status("Ready to draw", 'blue')
        self._update_polygon_list()
        self.fig.canvas.draw_idle()

    def _on_save_click(self, event):
        """Handle save button click"""
        if self.selected_polygon_idx is not None:
            # Update existing polygon
            self._update_selected_polygon()
        else:
            # Save new polygon
            self.save_current_polygon()

    def _update_selected_polygon(self):
        """Update the label/room_type of selected polygon"""
        if self.selected_polygon_idx is None:
            return

        idx = self.selected_polygon_idx
        new_label = self.label_textbox.text.strip()
        new_room = self.room_textbox.text.strip()

        if not new_label:
            new_label = f"polygon-{idx + 1:03d}"

        # Update data
        self.polygons[idx]['label'] = new_label
        self.polygons[idx]['room_type'] = new_room

        # Update visual label
        if idx < len(self.polygon_labels):
            self.polygon_labels[idx].set_text(new_label)

        self._update_status(f"Updated '{new_label}'", 'green')
        self._update_polygon_list()
        self.fig.canvas.draw_idle()

    def _on_clear_click(self, event):
        """Handle clear button click"""
        self._deselect_polygon()
        self.current_polygon_vertices = []
        self.selector.clear()
        self._update_status("Cleared - ready to draw new polygon", 'blue')
        self.fig.canvas.draw_idle()

    def _on_export_click(self, event):
        """Handle export button click"""
        self.save_all_annotations()

    def _on_delete_click(self, event):
        """Handle delete button click"""
        if self.selected_polygon_idx is None:
            self._update_status("No polygon selected to delete", 'red')
            return

        idx = self.selected_polygon_idx
        label = self.polygons[idx].get('label', 'unnamed')

        # Remove from data
        self.polygons.pop(idx)

        # Remove visual elements
        if idx < len(self.polygon_patches):
            self.polygon_patches[idx].remove()
            self.polygon_patches.pop(idx)
        if idx < len(self.polygon_labels):
            self.polygon_labels[idx].remove()
            self.polygon_labels.pop(idx)

        self._deselect_polygon()
        self._update_status(f"Deleted '{label}'", 'green')
        self._update_polygon_list()
        self.fig.canvas.draw_idle()

    def _on_reset_zoom_click(self, event):
        """Reset zoom to original view"""
        self.ax.set_xlim(self.original_xlim)
        self.ax.set_ylim(self.original_ylim)
        self._update_status("Zoom reset", 'blue')
        self.fig.canvas.draw_idle()

    def _on_quit_click(self, event):
        """Handle quit button click"""
        plt.close(self.fig)

    def _update_status(self, message, color='blue'):
        """Update status text"""
        self.status_text.set_text(f"Status: {message}")
        self.status_text.set_color(color)
        self.fig.canvas.draw_idle()

    def _update_polygon_list(self):
        """Update the list of saved polygons in the side panel"""
        self.ax_list.clear()
        self.ax_list.axis('off')

        if not self.polygons:
            self.ax_list.text(0, 0.95, "(no polygons saved)", fontsize=9, style='italic', color='gray')
        else:
            # Show up to 10 polygons
            max_display = 10
            for i, poly in enumerate(self.polygons[:max_display]):
                y_pos = 0.95 - (i * 0.095)
                label = poly.get('label', 'unnamed')
                room = poly.get('room_type', '')
                display_text = f"{i+1}. {label}"
                if room:
                    display_text += f" ({room})"
                # Truncate if too long
                if len(display_text) > 28:
                    display_text = display_text[:25] + "..."

                # Highlight selected
                if i == self.selected_polygon_idx:
                    self.ax_list.text(0, y_pos, display_text, fontsize=8,
                                     fontweight='bold', color='orange')
                else:
                    self.ax_list.text(0, y_pos, display_text, fontsize=8)

            if len(self.polygons) > max_display:
                self.ax_list.text(0, 0.02, f"... and {len(self.polygons) - max_display} more",
                                 fontsize=8, style='italic')

        self.fig.canvas.draw_idle()

    def on_polygon_select(self, vertices):
        """Callback when polygon is completed or modified"""
        if len(vertices) < 3:
            return

        self.current_polygon_vertices = vertices

        # Deselect any selected polygon when drawing new one
        if self.selected_polygon_idx is not None:
            self._deselect_polygon()

        # Calculate area in pixels
        poly_array = np.array(vertices)
        area_px = 0.5 * np.abs(np.dot(poly_array[:, 0], np.roll(poly_array[:, 1], 1)) -
                                np.dot(poly_array[:, 1], np.roll(poly_array[:, 0], 1)))

        self._update_status(f"Polygon ready: {len(vertices)} vertices, {area_px:.0f} px^2", 'green')

    def on_key_press(self, event):
        """Handle keyboard shortcuts"""
        # Ignore keys that PolygonSelector handles internally
        if event.key in ('backspace', 'delete', 'escape'):
            if event.key == 'escape':
                self._deselect_polygon()
            return
        if event.key == 's':
            if self.selected_polygon_idx is not None:
                self._update_selected_polygon()
            else:
                self.save_current_polygon()
        elif event.key == 'S':  # Shift+S
            self.save_all_annotations()
        elif event.key == 'l':
            self.load_annotations()
            self._update_polygon_list()
        elif event.key == 'c':
            self.calculate_statistics()
        elif event.key == 'd':
            self._on_delete_click(None)
        elif event.key == 'r':
            self._on_reset_zoom_click(None)
        elif event.key == 'q':
            plt.close(self.fig)

    def save_current_polygon(self):
        """Save the currently drawn polygon to storage"""
        if len(self.current_polygon_vertices) < 3:
            self._update_status("No polygon to save - draw one first", 'red')
            return

        # Get label from text box
        label = self.label_textbox.text.strip()
        if not label:
            label = f"polygon-{len(self.polygons) + 1:03d}"

        room_type = self.room_textbox.text.strip()

        polygon_data = {
            'id': f'polygon-{len(self.polygons):03d}',
            'label': label,
            'room_type': room_type,
            'vertices': [[float(x), float(y)] for x, y in self.current_polygon_vertices],
            'metadata': {}
        }

        self.polygons.append(polygon_data)

        # Draw saved polygon permanently
        poly = Polygon(
            self.current_polygon_vertices,
            closed=True,
            edgecolor='green',
            facecolor='green',
            alpha=0.3,
            linewidth=2
        )
        self.ax.add_patch(poly)
        self.polygon_patches.append(poly)

        # Add label text at polygon centroid
        vertices_array = np.array(self.current_polygon_vertices)
        centroid = vertices_array.mean(axis=0)
        label_text = self.ax.text(centroid[0], centroid[1], label,
                    color='white', fontsize=9,
                    bbox=dict(boxstyle='round', facecolor='green', alpha=0.7),
                    ha='center', va='center')
        self.polygon_labels.append(label_text)

        # Reset for next polygon
        self.current_polygon_vertices = []
        self.selector.clear()

        # Clear text boxes for next entry
        self.label_textbox.set_val('')
        self.room_textbox.set_val('')

        # Update UI
        self._update_polygon_list()
        self._update_status(f"Saved '{label}' ({len(self.polygons)} total)", 'green')
        self.fig.canvas.draw_idle()
        print(f"Saved polygon '{label}' ({len(self.polygons)} total)")

    def save_all_annotations(self):
        """Save all polygons to JSON file"""
        if not self.polygons:
            self._update_status("No polygons to export", 'red')
            return

        output_path = self.image_path.with_suffix('.json')

        annotation_data = {
            'image': {
                'filename': self.image_path.name,
                'width': self.image.shape[1],
                'height': self.image.shape[0]
            },
            'annotations': self.polygons
        }

        with open(output_path, 'w') as f:
            json.dump(annotation_data, f, indent=2)

        self._update_status(f"Exported {len(self.polygons)} to JSON", 'green')
        print(f"Saved {len(self.polygons)} annotations to {output_path}")

    def load_annotations(self):
        """Load existing annotations from JSON file"""
        json_path = self.image_path.with_suffix('.json')

        if not json_path.exists():
            print(f"No existing annotations found at {json_path}")
            return

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.polygons = data.get('annotations', [])
        self.polygon_patches = []
        self.polygon_labels = []

        # Draw loaded polygons
        for poly_data in self.polygons:
            vertices = poly_data['vertices']
            poly = Polygon(
                vertices,
                closed=True,
                edgecolor='green',
                facecolor='green',
                alpha=0.3,
                linewidth=2
            )
            self.ax.add_patch(poly)
            self.polygon_patches.append(poly)

            # Add label
            vertices_array = np.array(vertices)
            centroid = vertices_array.mean(axis=0)
            label_text = self.ax.text(centroid[0], centroid[1], poly_data.get('label', ''),
                        color='white', fontsize=9,
                        bbox=dict(boxstyle='round', facecolor='green', alpha=0.7),
                        ha='center', va='center')
            self.polygon_labels.append(label_text)

        self._update_status(f"Loaded {len(self.polygons)} polygons", 'green')
        self.fig.canvas.draw_idle()
        print(f"Loaded {len(self.polygons)} existing annotations")

    def calculate_statistics(self):
        """Calculate pixel statistics within current polygon"""
        if len(self.current_polygon_vertices) < 3:
            self._update_status("No polygon selected for stats", 'red')
            return

        # Create mask from polygon vertices
        mask = np.zeros(self.image.shape[:2], dtype=np.uint8)
        pts = np.array(self.current_polygon_vertices, dtype=np.int32)
        cv2.fillPoly(mask, [pts], (255,))

        # Extract pixel values (using grayscale for daylight analysis)
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        pixels = gray[mask > 0]

        # Calculate statistics
        stats = {
            'mean': float(np.mean(pixels)),
            'std': float(np.std(pixels)),
            'min': float(np.min(pixels)),
            'max': float(np.max(pixels)),
            'median': float(np.median(pixels)),
            'area_pixels': int(np.sum(mask > 0)),
            'percentile_5': float(np.percentile(pixels, 5)),
            'percentile_95': float(np.percentile(pixels, 95))
        }

        print("\n=== Pixel Statistics ===")
        for key, value in stats.items():
            print(f"{key:15s}: {value:.2f}")
        print("========================\n")

        self._update_status(f"Stats: mean={stats['mean']:.1f}, area={stats['area_pixels']}px", 'blue')

    def show(self):
        """Display the annotation interface"""
        print("\n=== Polygon Annotator ===")
        print("Draw polygons on the image, enter labels in the side panel")
        print("Scroll wheel: zoom in/out")
        print("Right-click: select existing polygon")
        print("Keyboard: s=save, S=export, d=delete, r=reset zoom, q=quit")
        print("=========================\n")
        plt.show()


def select_image_file(start_dir=None):
    """Open file dialog to select an image"""
    root = Tk()
    root.withdraw()  # Hide the root window

    if start_dir is None:
        start_dir = Path.cwd()

    file_path = filedialog.askopenfilename(
        initialdir=start_dir,
        title="Select Floor Plan Image",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
            ("PNG files", "*.png"),
            ("All files", "*.*")
        ]
    )

    root.destroy()
    return file_path


if __name__ == "__main__":
    import sys

    # Check for command-line argument first
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Fall back to file dialog
        script_dir = Path(__file__).parent
        print("Select an image file to annotate...")
        image_path = select_image_file(start_dir=script_dir)

    if image_path:
        print(f"Loading image: {image_path}")
        annotator = PolygonAnnotator(image_path)
        annotator.show()
    else:
        print("No file selected. Exiting.")
