"""Encryption module for ShareBox."""

import os
import hashlib
import secrets
from typing import Optional
from getpass import getpass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from .logging_config import get_logger


logger = get_logger(__name__)


class EncryptionManager:
    """Handles client-side encryption for ShareBox."""
    
    def __init__(self, config: dict):
        """Initialize encryption manager.
        
        Args:
            config: Encryption configuration
        """
        self.config = config
        self.algorithm = config.get('algorithm', 'AES-256-GCM')
        self.key = None
        
        # Get or prompt for password
        password = config.get('password', '')
        if not password:
            password = getpass("Enter encryption password: ")
        
        if not password:
            raise ValueError("Encryption password is required")
        
        # Derive encryption key from password
        self.key = self._derive_key(password)
        
        logger.info("Encryption manager initialized")
    
    def _derive_key(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """Derive encryption key from password using PBKDF2.
        
        Args:
            password: User password
            salt: Salt for key derivation (generated if None)
            
        Returns:
            32-byte encryption key
        """
        if salt is None:
            # Generate a consistent salt based on password
            # This ensures the same password always generates the same key
            salt = hashlib.sha256(password.encode()).digest()[:16]
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        return kdf.derive(password.encode())
    
    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data using AES-256-GCM.
        
        Args:
            data: Raw data to encrypt
            
        Returns:
            Encrypted data with nonce prepended
        """
        try:
            # Generate a random nonce
            nonce = secrets.token_bytes(12)  # 96 bits for GCM
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce),
                backend=default_backend()
            )
            
            encryptor = cipher.encryptor()
            
            # Encrypt data
            ciphertext = encryptor.update(data) + encryptor.finalize()
            
            # Prepend nonce and auth tag to ciphertext
            encrypted_data = nonce + encryptor.tag + ciphertext
            
            logger.debug(f"Encrypted {len(data)} bytes to {len(encrypted_data)} bytes")
            return encrypted_data
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt data using AES-256-GCM.
        
        Args:
            encrypted_data: Encrypted data with nonce and tag prepended
            
        Returns:
            Decrypted raw data
        """
        try:
            if len(encrypted_data) < 28:  # 12 (nonce) + 16 (tag) minimum
                raise ValueError("Invalid encrypted data format")
            
            # Extract nonce, tag, and ciphertext
            nonce = encrypted_data[:12]
            tag = encrypted_data[12:28]
            ciphertext = encrypted_data[28:]
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce, tag),
                backend=default_backend()
            )
            
            decryptor = cipher.decryptor()
            
            # Decrypt data
            data = decryptor.update(ciphertext) + decryptor.finalize()
            
            logger.debug(f"Decrypted {len(encrypted_data)} bytes to {len(data)} bytes")
            return data
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Decryption failed: {e}")
    
    def encrypt_filename(self, filename: str) -> str:
        """Encrypt filename for additional privacy.
        
        Args:
            filename: Original filename
            
        Returns:
            Encrypted filename (base64 encoded)
        """
        try:
            import base64
            
            # Encrypt filename
            encrypted = self.encrypt(filename.encode('utf-8'))
            
            # Return base64 encoded (safe for filesystem)
            return base64.urlsafe_b64encode(encrypted).decode('ascii')
            
        except Exception as e:
            logger.error(f"Filename encryption failed: {e}")
            # Fallback to original filename if encryption fails
            return filename
    
    def decrypt_filename(self, encrypted_filename: str) -> str:
        """Decrypt filename.
        
        Args:
            encrypted_filename: Encrypted filename (base64 encoded)
            
        Returns:
            Original filename
        """
        try:
            import base64
            
            # Decode from base64
            encrypted = base64.urlsafe_b64decode(encrypted_filename.encode('ascii'))
            
            # Decrypt filename
            decrypted = self.decrypt(encrypted)
            
            return decrypted.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Filename decryption failed: {e}")
            # Fallback to encrypted filename if decryption fails
            return encrypted_filename
    
    def verify_password(self, password: str) -> bool:
        """Verify if the provided password is correct.
        
        Args:
            password: Password to verify
            
        Returns:
            True if password is correct, False otherwise
        """
        try:
            test_key = self._derive_key(password)
            return test_key == self.key
        except Exception:
            return False
    
    def change_password(self, old_password: str, new_password: str) -> bool:
        """Change encryption password.
        
        Args:
            old_password: Current password
            new_password: New password
            
        Returns:
            True if password changed successfully, False otherwise
        """
        try:
            # Verify old password
            if not self.verify_password(old_password):
                logger.error("Old password verification failed")
                return False
            
            # Generate new key
            self.key = self._derive_key(new_password)
            
            logger.info("Encryption password changed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Password change failed: {e}")
            return False
    
    def get_encryption_info(self) -> dict:
        """Get encryption information.
        
        Returns:
            Dictionary with encryption details
        """
        return {
            'algorithm': self.algorithm,
            'key_length': len(self.key) * 8,  # bits
            'enabled': True
        } 