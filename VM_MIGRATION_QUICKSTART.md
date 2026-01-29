# VM Migration Quick Start Guide (Ubuntu)

This is a condensed version of the full migration guide optimized for **Ubuntu VMs**. For detailed instructions, see [VM_MIGRATION_GUIDE.md](./VM_MIGRATION_GUIDE.md).

> **Note**: This guide assumes Ubuntu 20.04, 22.04, or 24.04 LTS.

## 🚀 Quick Migration Steps

### On Local Machine

1. **Export MongoDB Data**
   ```bash
   cd /Users/gwl/Desktop/QPPChatbot
   ./scripts/export_mongodb.sh
   ```

2. **Prepare Project Archive**
   ```bash
   cd /Users/gwl/Desktop/QPPChatbot
   tar --exclude='venv' --exclude='__pycache__' --exclude='node_modules' \
       -czf ~/qppchatbot_backup.tar.gz .
   ```

3. **Transfer Files to VM**
   ```bash
   scp ~/mongodb_backup/mongodb_export_*.tar.gz user@vm_ip:/tmp/
   scp ~/qppchatbot_backup.tar.gz user@vm_ip:/tmp/
   ```

### On VM

1. **Check Ubuntu Version & Install MongoDB**
   ```bash
   # Check Ubuntu version
   lsb_release -cs
   
   # Install MongoDB (auto-detects Ubuntu version)
   UBUNTU_CODENAME=$(lsb_release -cs)
   curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
   echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu ${UBUNTU_CODENAME}/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
   sudo apt update && sudo apt install -y mongodb-org
   sudo systemctl enable mongod && sudo systemctl start mongod
   ```

2. **Extract Files**
   ```bash
   cd /tmp
   tar -xzf mongodb_export_*.tar.gz
   cd /opt/qppchatbot
   tar -xzf /tmp/qppchatbot_backup.tar.gz
   ```

3. **Import MongoDB Data**
   ```bash
   cd /opt/qppchatbot
   ./scripts/import_mongodb.sh /tmp/mongodb_export_*/
   ```

4. **Set Up Project**
   ```bash
   cd /opt/qppchatbot
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip setuptools wheel
   # Install system dependencies
   sudo apt install -y libpq-dev gcc g++ libffi-dev libssl-dev
   pip install -r requirements.txt
   ```

5. **Configure**
   ```bash
   # Create .env file or update config.py
   nano config.py
   ```

6. **Test**
   ```bash
   source venv/bin/activate
   python3 test_mongodb_connection.py
   ```

## 📝 Key Configuration

Update `config.py` or create `.env`:

```bash
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=legal_cases_v2
```

## ✅ Verification

```bash
# Check MongoDB
sudo systemctl status mongod
mongosh --eval "use legal_cases_v2; db.documents.countDocuments()"

# Test connection
cd /opt/qppchatbot
source venv/bin/activate
python3 test_mongodb_connection.py
```

## 🔧 Troubleshooting

- **MongoDB not running**: `sudo systemctl start mongod`
- **Permission issues**: `sudo chown -R $USER:$USER /opt/qppchatbot`
- **Import fails**: Check export directory path and MongoDB is running

For detailed troubleshooting, see [VM_MIGRATION_GUIDE.md](./VM_MIGRATION_GUIDE.md).

