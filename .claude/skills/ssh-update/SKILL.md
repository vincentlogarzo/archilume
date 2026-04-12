# SSH Update Skill
User will provide a new IP address and optionally a VM name.
1. Read ~/.ssh/config
2. Update the matching Host entry with the new IP (HostName field)
3. Ensure User is set to the existing User value (or ask if not present)
4. Ensure IdentityFile points to the correct key
5. Show the updated entry for confirmation
