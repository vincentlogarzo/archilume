import os
import re

from dataclasses import dataclass, field

@dataclass
class AddMissingModifiers:
    """
    Processes a Radiance .rad file and an accompanying .mtl file to find
    modifiers defined in the .rad file that are missing from the .mtl file,
    and appends default definitions for them.
    """

    rad_filepath: str
    mtl_filepath: str

    # These fields are for internal state and results, not constructor arguments.
    # They are initialized via default_factory or in __post_init__.
    modifiers: list[str] = field(init=False, default_factory=list)
    # missing_materials is initialized as an empty list.
    # It can be set to None by _find_missing_modifiers to indicate an error during its computation.
    missing_materials: list[str] | None = field(init=False, default_factory=list)

    def __post_init__(self):
        """
        Post-initialization checks, primarily for file existence.
        This method is automatically called after the dataclass __init__.
        """
        if not os.path.exists(self.rad_filepath):
            raise FileNotFoundError(f".rad file not found: {self.rad_filepath}")
        if not os.path.exists(self.mtl_filepath):
            raise FileNotFoundError(f"Radiance .mtl file not found: {self.mtl_filepath}")

    def __get_modifiers_from_rad(self) -> bool:
        """
        Extracts unique modifiers from the .rad file and stores them in self.modifiers.

        Returns:
            bool: True if successful, False otherwise.
        """
        extracted_words = set()
        blank_line_found = False
        try:
            with open(self.rad_filepath, encoding="utf-8") as file:
                for line in file:
                    line = line.rstrip("\n")
                    if not line.strip():
                        blank_line_found = True
                    elif blank_line_found:
                        words = line.split()
                        if words:
                            extracted_words.add(words[0])
                        blank_line_found = False
            self.modifiers = sorted(list(extracted_words))  # Store sorted list
            return True
        except Exception as e:
            print(f"An error occurred while reading {self.rad_filepath}: {e}")
            self.modifiers = []  # Ensure it's an empty list on error
            return False

    def __find_missing_modifiers(self) -> bool:
        """
        Finds unique material names from self.modifiers not in the Radiance .mtl file.
        Stores them in self.missing_materials. If an error occurs, self.missing_materials is set to None.

        Returns:
            bool: True if successful (even if no missing materials), False on error.
        """
        if not self.modifiers:  # No modifiers to check against
            self.missing_materials = []
            return True

        current_missing_materials = []
        try:
            with open(self.mtl_filepath, encoding="utf-8") as file:
                radiance_mtl_content = file.read()
                radiance_defined_materials = set(
                    re.findall(r"void\s+\w+\s+(\w+)", radiance_mtl_content)
                )

            for material_name in self.modifiers:
                if material_name not in radiance_defined_materials:
                    current_missing_materials.append(material_name)

            self.missing_materials = sorted(
                list(set(current_missing_materials))
            )  # Store sorted list
            return True
        except Exception as e:
            print(
                f"An error occurred while reading or parsing the Radiance MTL file ({self.mtl_filepath}): {e}"
            )
            self.missing_materials = None  # Indicate an error state
            return False

    def __append_missing_modifiers(self) -> bool:
        """
        Appends default Radiance material definitions for self.missing_materials
        to the .mtl file if they are not already present.

        Returns:
            bool: True if successful or no materials to append, False on error.
        """

        def _default_radiance_material(material_name: str) -> list[str]:
            return [
                f"# {material_name}",
                f"void plastic {material_name}",
                "0",
                "0",
                "5 0.5 0.5 0.5 0.0 0.0",  # Default grey plastic
                "",
            ]

        if self.missing_materials is None:
            print("Cannot append materials: an error occurred when finding missing materials.")
            return False

        if not self.missing_materials:
            return True

        try:
            with open(self.mtl_filepath, "r+", encoding="utf-8") as file:
                content = file.read()
                existing_defined_materials = set(re.findall(r"void\s+\w+\s+(\w+)", content))

                materials_to_actually_append = [
                    mat for mat in self.missing_materials if mat not in existing_defined_materials
                ]

                if materials_to_actually_append:
                    file.seek(0, os.SEEK_END)
                    if content and not content.endswith(
                        ("\n", "\r\n")
                    ):  # Check for existing newline
                        file.write("\n")

                    file.write("\n# Default materials added for missing modifiers:\n")
                    for material_name in materials_to_actually_append:
                        material_definition = _default_radiance_material(material_name)
                        for line_content in material_definition:
                            file.write(line_content + "\n")
                    print(f"{len(materials_to_actually_append)} default material(s) appended.")
                else:
                    print(
                        "All previously identified missing materials are already defined or no new materials to append."
                    )
            return True
        except Exception as e:
            print(f"An error occurred while writing to {self.mtl_filepath}: {e}")
            return False

    def process_files(self) -> None:
        """
        Main processing method to find and append missing modifiers.
        """
        print(f"Processing .rad file: {self.rad_filepath}")
        print(f"Processing .mtl file: {self.mtl_filepath}")

        if not self.__get_modifiers_from_rad():
            print("Failed to get modifiers from .rad file. Aborting.")
            return

        if self.modifiers:
            print(
                f"\nFound {len(self.modifiers)} unique modifier(s) in {os.path.basename(self.rad_filepath)}."
            )
        else:
            print(f"\nNo modifiers found in {os.path.basename(self.rad_filepath)}.")
            return

        if not self.__find_missing_modifiers():
            print("Failed to find missing modifiers. Aborting.")
            return

        if self.missing_materials is None:
            print("\nError occurred during material comparison. Cannot proceed with appending.")
        elif self.missing_materials:
            print(
                f"\nFound {len(self.missing_materials)} missing material(s) that need definitions in {os.path.basename(self.mtl_filepath)}:"
            )
            for material_name in self.missing_materials:
                print(f"  {material_name}")

            if self.__append_missing_modifiers():
                print(f"\nSuccessfully processed missing materials for {self.mtl_filepath}")
            else:
                print(f"\nFailed to append default materials to {self.mtl_filepath}.")
        else:
            print(
                f"\nAll modifiers from {os.path.basename(self.rad_filepath)} were found in {os.path.basename(self.mtl_filepath)}."
            )

        print("\nProcessing complete.")