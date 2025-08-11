# Archilume imports
from archilume.add_missing_modifiers import AddMissingModifiers

# Standard library imports
import os
import subprocess
from dataclasses import dataclass

#TODO: shoul dbe allowed to take in multiple .obj file for site and bld and also convert their respectie .mtl files.

@dataclass
class ObjToOctree:
    """
    Converts material definitions from a Wavefront .mtl file
    (e.g., exported from Revit) into a Radiance material description file.

    The converter processes common .mtl properties like diffuse color ('Kd')
    and dissolve/opacity ('d') to create Radiance 'plastic' (for opaque)
    or 'glass' (for transparent/translucent) materials.

    Attributes:
        mtl_file_path (str): The full path to the input .mtl file used for conversion.
        output_file_name (str | None): The full path to the generated Radiance .mtl file.
                                     This is set upon successful conversion, otherwise None.
        converted_content (str | None): The Radiance formatted string of the materials.
                                       Set upon successful conversion, otherwise None.
    """

    # User inputs
    input_mtl_file_path: str | None = None
    obj_file_path: str | None = None

    # variables for use within class functions
    radiance_mtl_file_path: str | None = None
    rad_file_path: str | None = None

    def __convert_mtl_materials(self, mtl_content: str) -> str:  # <-- Added self
        """
        Converts .mtl material entries to Radiance material format.
        Args:
            mtl_content: The content of the .mtl file as a string.
        Returns:
            The converted content as a string.
        """

        def _format_radiance_glass(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void glass {name}",
                "0",
                "0",
                f"3 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f}",
            ]

        def _format_radiance_plastic(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void plastic {name}",
                "0",
                "0",
                f"5 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f} 0.000 0.005",
            ]

        lines = mtl_content.splitlines()
        converted_lines = ["# Third line parameters: R G B Sp Rg"]
        current_material = {}

        for line in lines:
            line = line.strip()
            if line.startswith("newmtl"):
                if current_material:
                    if current_material.get("d", 1.0) < 1.0:
                        converted_lines.extend(_format_radiance_glass(current_material))
                    elif current_material.get("d", 1.0) == 1.0:
                        converted_lines.extend(_format_radiance_plastic(current_material))
                material_name = line.split(" ", 1)[1]
                current_material = {"name": material_name}
            elif line.startswith("Kd"):
                current_material["Kd"] = [float(x) for x in line.split()[1:]]
            elif line.startswith("d"):
                current_material["d"] = float(line.split()[1])
            elif line and not line.startswith("#"):
                pass

        if current_material:
            if current_material.get("d", 1.0) < 1.0:
                converted_lines.extend(_format_radiance_glass(current_material))
            elif current_material.get("d", 1.0) == 1.0:
                converted_lines.extend(_format_radiance_plastic(current_material))

        return "\n".join(converted_lines)

    def parse_mtl_file(self) -> None:
        """
        Read .mtl file specified by mtl_file_to_parse, convert its content, and save.
        Updates the instance's mtl_file_path, output_file_name, and converted_content.

        Args:
            mtl_file_to_parse (str): The full path to the .mtl file to parse.
        """

        try:
            with open(self.input_mtl_file_path) as file:
                mtl_content = file.read()

            # Call instance method convert_mtl_materials using self
            converted_content = self.__convert_mtl_materials(mtl_content)  # <-- Use self.

            # Create the output file name
            # Use self.input_mtl_file_path for deriving output name
            self.radiance_mtl_file_path = (
                os.path.splitext(self.input_mtl_file_path)[0] + "_radiance.mtl"
            )

            # Write the output to the new file
            with open(self.radiance_mtl_file_path, "w") as output_file:
                output_file.write("#Radiance Map file:\n")
                output_file.write(converted_content)

            print(f"Radiance material file created: {self.radiance_mtl_file_path}")

        except FileNotFoundError:
            # Use self.mtl_file_path in error message
            print(f"Error: File not found at {self.radiance_mtl_file_path}")
        except Exception as e:
            print(f"An error occurred: {e}")

    def obj_to_rad(self, obj_file_to_parse: str, mtl_file_to_parse: str) -> None:
        """
        convert obj file to radiance description file ready to be compiled into an octree for rendering scenes.
        obj2rad "C:\\VE Projects\\! - code\\Run 1\1_obj_and_sky_to_oct\222050_R22_86 COWLES RD.obj" > 222050_R22_86 COWLES RD.rad
        Obj files must be exported from Revit in meters not mm.
        """

        self.obj_file_path = obj_file_to_parse  # Set/update the instance attribute
        self.input_mtl_file_path = mtl_file_to_parse  # Set/update the instance attribute

        try:
            output_rad_file_name = obj_file_to_parse.replace(".obj", ".rad")
            self.rad_file_path = output_rad_file_name

            print(f"Attempting to convert \n {obj_file_to_parse} \n to \n {output_rad_file_name}")
            # Ensure the rad_file directory exists

            os.makedirs(os.path.dirname(output_rad_file_name), exist_ok=True)

            # Run the obj2rad command
            command = ["obj2rad", obj_file_to_parse]
            with open(output_rad_file_name, "w") as rad_output:
                subprocess.run(command, stdout=rad_output, check=True)

            # Verify if the rad_file was created
            if not os.path.exists(output_rad_file_name):
                raise FileNotFoundError(f"Expected RAD file not found: {output_rad_file_name}")
            print(f"Successfully converted \n {obj_file_to_parse} \n to \n {output_rad_file_name}")
            print(
                f"Attempting to add missing modifiers to \n {self.radiance_mtl_file_path} \n from \\ n {self.rad_file_path}"
            )

            # parse original .mtl file
            self.parse_mtl_file()

            AddMissingModifiers(self.rad_file_path, self.radiance_mtl_file_path).process_files()

        except Exception as e:
            print(f"Error converting {obj_file_to_parse} \n to \n {output_rad_file_name}: {e}")
            raise

    def rad_to_octree(self, output_dir: str = "octrees") -> None:
        """
        Runs the oconv command to generate frozen skyless octree for use in rendering. Sky file will be added just prior to rendering.
        must use command prompt intead of powershell in vs code as its default coding is utf-8
        Example from IESVE
        To use the below command prompt, a sky file must be added. Note that the rest of this function produces skyless octress for later processing with sunny sky files.
        oconv -f sky/Jun21_1100_ss.sky lib/87example_radiance.mtl lib/87cowles.rad > octrees/87_example_Jun21_1100_ss.oct
        oconv -f lib\87cowles_noWindows_radiance.mtl lib\87cowles_noWindows.obj
        """

        geometry_rad_base = os.path.basename(self.rad_file_path)
        geometry_rad_base_no_ext = os.path.splitext(geometry_rad_base)[0]

        output_filename = os.path.join(output_dir, f"{geometry_rad_base_no_ext}_skyless.oct")
        command = ["oconv", "-f", self.radiance_mtl_file_path, self.rad_file_path]
        with open(output_filename, "w") as outfile:
            process = subprocess.Popen(command, stdout=outfile, stderr=subprocess.PIPE)
            _, stderr = process.communicate()

        if stderr:
            print(f"Error running oconv : {stderr.decode()}")
        else:
            print(f"Successfully generated: {output_filename}")
