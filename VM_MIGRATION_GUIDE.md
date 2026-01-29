# VM Migration Guide - QPPChatbot with MongoDB

This guide will help you migrate your entire QPPChatbot project and MongoDB data to a Virtual Machine (VM).

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Prepare Your Local Machine](#step-1-prepare-your-local-machine)
3. [Step 2: Set Up VM](#step-2-set-up-vm)
4. [Step 3: Install MongoDB on VM](#step-3-install-mongodb-on-vm)
5. [Step 4: Export MongoDB Data from Local Machine](#step-4-export-mongodb-data-from-local-machine)
6. [Step 5: Transfer Files to VM](#step-5-transfer-files-to-vm)
7. [Step 6: Import MongoDB Data on VM](#step-6-import-mongodb-data-on-vm)
8. [Step 7: Set Up Project on VM](#step-7-set-up-project-on-vm)
9. [Step 8: Configure and Test](#step-8-configure-and-test)
10. [Step 9: Set Up Services (Optional)](#step-9-set-up-services-optional)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Local machine with MongoDB running
- **Ubuntu VM** (20.04 LTS, 22.04 LTS, or 24.04 LTS recommended)
- SSH access to the VM
- Basic knowledge of Linux commands
- MongoDB data export tools (`mongodump`)

> **Note**: This guide is optimized for Ubuntu. If you're using a different Linux distribution, adjust package manager commands accordingly.

---

## Step 1: Prepare Your Local Machine

### 1.1 Check MongoDB Status

```bash
# On your local machine (macOS)
# Check if MongoDB is running
brew services list | grep mongodb

# Or check MongoDB process
ps aux | grep mongod

# If not running, start it
brew services start mongodb-community
```

### 1.2 Verify MongoDB Connection

```bash
# Test MongoDB connection
mongosh --eval "db.adminCommand('ping')"

# List databases
mongosh --eval "show dbs"

# Check your database exists
mongosh --eval "use legal_cases_v2; db.getName()"
```

### 1.3 Export MongoDB Data

**Option A: Using the Helper Script (Recommended)**

```bash
# Navigate to project directory
cd /Users/gwl/Desktop/QPPChatbot

# Run the export script
./scripts/export_mongodb.sh

# The script will:
# - Check MongoDB connection
# - Export the database
# - Create a compressed archive
# - Show export statistics
```

**Option B: Manual Export**

```bash
# Create backup directory
mkdir -p ~/mongodb_backup
cd ~/mongodb_backup

# Export entire database (recommended)
mongodump --host localhost --port 27017 --db legal_cases_v2 --out ./mongodb_export_$(date +%Y%m%d_%H%M%S)

# If you have authentication enabled:
# mongodump --host localhost --port 27017 --username YOUR_USERNAME --password YOUR_PASSWORD --authenticationDatabase admin --db legal_cases_v2 --out ./mongodb_export_$(date +%Y%m%d_%H%M%S)

# Verify export was successful
ls -lh ./mongodb_export_*/
```

### 1.4 Prepare Project Files

```bash
# Navigate to project directory
cd /Users/gwl/Desktop/QPPChatbot

# Create a tarball of the project (excluding venv and __pycache__)
tar --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='dist' \
    -czf ~/qppchatbot_backup.tar.gz .

# Verify the archive
ls -lh ~/qppchatbot_backup.tar.gz
```

---

## Step 2: Set Up VM

### 2.1 Connect to VM

```bash
# SSH into your VM
ssh username@vm_ip_address

# Example:
# ssh ubuntu@192.168.1.100
```

### 2.2 Check Ubuntu Version

```bash
# Check Ubuntu version
lsb_release -a

# Or
cat /etc/os-release
```

**Note**: MongoDB repository setup varies by Ubuntu version. The guide uses Ubuntu 22.04 (Jammy) as default. Adjust the repository URL if needed:
- Ubuntu 20.04 (Focal): `focal/mongodb-org/7.0`
- Ubuntu 22.04 (Jammy): `jammy/mongodb-org/7.0`
- Ubuntu 24.04 (Noble): `noble/mongodb-org/7.0`

### 2.3 Update System

```bash
# Update package lists
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget git build-essential software-properties-common
```

### 2.4 Create Project Directory

```bash
# Create directory for the project
sudo mkdir -p /opt/qppchatbot
sudo chown $USER:$USER /opt/qppchatbot

# Create MongoDB data directory
sudo mkdir -p /var/lib/mongodb
sudo chown mongodb:mongodb /var/lib/mongodb

# Create MongoDB log directory
sudo mkdir -p /var/log/mongodb
sudo chown mongodb:mongodb /var/log/mongodb
```

---

## Step 3: Install MongoDB on VM

### 3.1 Install MongoDB on Ubuntu

**First, determine your Ubuntu version:**

```bash
# Get Ubuntu codename
UBUNTU_CODENAME=$(lsb_release -cs)
echo "Ubuntu codename: $UBUNTU_CODENAME"
```

**Then install MongoDB:**

```bash
# Import MongoDB public GPG key
curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

# Detect Ubuntu version and set repository
UBUNTU_CODENAME=$(lsb_release -cs)
echo "Detected Ubuntu version: $UBUNTU_CODENAME"

# Add MongoDB repository (adjust codename if needed)
# For Ubuntu 20.04 (Focal): use 'focal'
# For Ubuntu 22.04 (Jammy): use 'jammy'  
# For Ubuntu 24.04 (Noble): use 'noble'
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu ${UBUNTU_CODENAME}/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

# Update package lists
sudo apt update

# Install MongoDB
sudo apt install -y mongodb-org

# Pin MongoDB version to prevent auto-updates
echo "mongodb-org hold" | sudo dpkg --set-selections
echo "mongodb-org-database hold" | sudo dpkg --set-selections
echo "mongodb-org-server hold" | sudo dpkg --set-selections
echo "mongodb-mongosh hold" | sudo dpkg --set-selections
echo "mongodb-org-mongos hold" | sudo dpkg --set-selections
echo "mongodb-org-tools hold" | sudo dpkg --set-selections

# Verify installation
mongod --version
mongosh --version
```

### 3.2 Configure MongoDB

```bash
# Edit MongoDB configuration
sudo nano /etc/mongod.conf
```

Update the configuration file:

```yaml
# /etc/mongod.conf
storage:
  dbPath: /var/lib/mongodb
  journal:
    enabled: true

systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log

net:
  port: 27017
  bindIp: 127.0.0.1  # Change to 0.0.0.0 if you need remote access

processManagement:
  timeZoneInfo: /usr/share/zoneinfo
```

### 3.3 Start MongoDB Service

```bash
# Enable MongoDB to start on boot
sudo systemctl enable mongod

# Start MongoDB service
sudo systemctl start mongod

# Check MongoDB status
sudo systemctl status mongod

# Verify MongoDB is running
mongosh --eval "db.adminCommand('ping')"
```

### 3.4 (Optional) Set Up MongoDB Authentication

```bash
# Connect to MongoDB
mongosh

# Switch to admin database
use admin

# Create admin user
db.createUser({
  user: "admin",
  pwd: "your_secure_password_here",
  roles: [ { role: "userAdminAnyDatabase", db: "admin" }, "readWriteAnyDatabase" ]
})

# Create application user
use legal_cases_v2
db.createUser({
  user: "qppchatbot_user",
  pwd: "your_app_password_here",
  roles: [ { role: "readWrite", db: "legal_cases_v2" } ]
})

# Exit MongoDB shell
exit
```

If you set up authentication, update `/etc/mongod.conf`:

```yaml
security:
  authorization: enabled
```

Then restart MongoDB:

```bash
sudo systemctl restart mongod
```

---

## Step 4: Export MongoDB Data from Local Machine

If you haven't done this already (from Step 1.3), do it now:

```bash
# On your local machine
cd ~/mongodb_backup

# Export database
mongodump --host localhost --port 27017 --db legal_cases_v2 --out ./mongodb_export_$(date +%Y%m%d_%H%M%S)

# Create compressed archive
tar -czf mongodb_export.tar.gz mongodb_export_*/
```

---

## Step 5: Transfer Files to VM

### 5.1 Transfer MongoDB Backup

```bash
# From your local machine, transfer MongoDB backup
scp ~/mongodb_backup/mongodb_export.tar.gz username@vm_ip_address:/tmp/

# Or if you have the export directory:
scp -r ~/mongodb_backup/mongodb_export_* username@vm_ip_address:/tmp/
```

### 5.2 Transfer Project Files

```bash
# From your local machine, transfer project archive
scp ~/qppchatbot_backup.tar.gz username@vm_ip_address:/tmp/
```

### 5.3 Extract Files on VM

```bash
# SSH into VM
ssh username@vm_ip_address

# Extract MongoDB backup
cd /tmp
tar -xzf mongodb_export.tar.gz

# Extract project files
cd /opt/qppchatbot
tar -xzf /tmp/qppchatbot_backup.tar.gz

# Verify files
ls -la /opt/qppchatbot
```

---

## Step 6: Import MongoDB Data on VM

### 6.1 Import Database

**Option A: Using the Helper Script (Recommended)**

```bash
# Extract the archive first (if you transferred a .tar.gz file)
cd /tmp
tar -xzf mongodb_export_*.tar.gz

# Run the import script
cd /opt/qppchatbot
./scripts/import_mongodb.sh /tmp/mongodb_export_*/

# Or if you want to drop existing database first:
MONGODB_DROP_EXISTING=true ./scripts/import_mongodb.sh /tmp/mongodb_export_*/
```

**Option B: Manual Import**

```bash
# Find the export directory
cd /tmp
ls -la mongodb_export_*/

# Import database (replace with actual directory name)
mongorestore --host localhost --port 27017 --db legal_cases_v2 /tmp/mongodb_export_*/legal_cases_v2

# If you set up authentication:
# mongorestore --host localhost --port 27017 --username qppchatbot_user --password your_app_password_here --authenticationDatabase legal_cases_v2 --db legal_cases_v2 /tmp/mongodb_export_*/legal_cases_v2
```

### 6.2 Verify Import

```bash
# Connect to MongoDB
mongosh

# Switch to your database
use legal_cases_v2

# List collections
show collections

# Check document counts
db.documents.countDocuments()
db.cases.countDocuments()
db.chat_sessions.countDocuments()

# Exit MongoDB shell
exit
```

---

## Step 7: Set Up Project on VM

### 7.1 Install Python and Dependencies

```bash
# Check Python version (Ubuntu 20.04+ comes with Python 3.8+)
python3 --version

# Install Python 3.9+ and pip (if not already installed)
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Ubuntu 20.04 may need Python 3.9 from deadsnakes PPA
# For Ubuntu 22.04+, Python 3.10+ is included by default
if [ "$(lsb_release -rs)" = "20.04" ]; then
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.9 python3.9-venv python3.9-dev
    # Use python3.9 instead of python3
    PYTHON_CMD=python3.9
else
    PYTHON_CMD=python3
fi

# Navigate to project directory
cd /opt/qppchatbot

# Create virtual environment
$PYTHON_CMD -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install MongoDB driver (if not in requirements.txt)
pip install pymongo

# Install system dependencies for some Python packages
sudo apt install -y libpq-dev gcc g++ libffi-dev libssl-dev

# Install all project dependencies
pip install -r requirements.txt
```

### 7.2 Install PostgreSQL (if needed)

```bash
# Install PostgreSQL (Ubuntu includes PostgreSQL 12+ by default)
sudo apt install -y postgresql postgresql-contrib

# Check PostgreSQL version
sudo -u postgres psql --version

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Check PostgreSQL status
sudo systemctl status postgresql

# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE legal_case_v2_1;
CREATE USER postgres WITH PASSWORD 'your_postgres_password';
ALTER ROLE postgres SET client_encoding TO 'utf8';
ALTER ROLE postgres SET default_transaction_isolation TO 'read committed';
ALTER ROLE postgres SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE legal_case_v2_1 TO postgres;
\q
EOF

# Run schema creation script (if you have one)
# sudo -u postgres psql -d legal_case_v2_1 -f postgres/schema_minimal.sql
```

### 7.3 Install Node.js (for frontend)

```bash
# Install Node.js 18+ (using NodeSource repository)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installation
node --version
npm --version

# Install frontend dependencies (if needed)
cd /opt/qppchatbot/chat-companion-hub
npm install
```

---

## Step 8: Configure and Test

### 8.1 Update Configuration

```bash
# Edit config.py or create .env file
cd /opt/qppchatbot
nano config.py
```

Update MongoDB configuration in `config.py`:

```python
# MongoDB Configuration
MONGODB_CONFIG = {
    'host': os.getenv('MONGODB_HOST', 'localhost'),  # Keep as localhost if MongoDB is on same VM
    'port': int(os.getenv('MONGODB_PORT', '27017')),
    'database': os.getenv('MONGODB_DATABASE', 'legal_cases_v2'),
    'username': os.getenv('MONGODB_USERNAME', None),  # Set if you enabled auth
    'password': os.getenv('MONGODB_PASSWORD', None)   # Set if you enabled auth
}
```

Or create a `.env` file:

```bash
cat > /opt/qppchatbot/.env << EOF
# Database Configuration
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_PORT=5432

# MongoDB Configuration
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=legal_cases_v2
MONGODB_USERNAME=qppchatbot_user
MONGODB_PASSWORD=your_app_password_here

# API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key
GROQ_API_KEY=your_groq_api_key

# Storage Paths
STORAGE_PATH=/opt/qppchatbot/storage
DOCUMENTS_PATH=/opt/qppchatbot/documents

# Other Settings
LOG_LEVEL=INFO
DEBUG=False
EOF
```

### 8.2 Create Storage Directories

```bash
cd /opt/qppchatbot
mkdir -p storage documents
chmod 755 storage documents
```

### 8.3 Test MongoDB Connection

```bash
# Activate virtual environment
source venv/bin/activate

# Test MongoDB connection
python3 test_mongodb_connection.py

# Or test manually
python3 << EOF
from mongo_manager import MongoManager

try:
    with MongoManager() as mongo:
        print("✓ MongoDB connection successful!")
        print(f"Database: {mongo.config['database']}")
        # Test a simple query
        doc_count = mongo.db.documents.count_documents({})
        print(f"Documents in database: {doc_count}")
except Exception as e:
    print(f"✗ MongoDB connection failed: {e}")
EOF
```

### 8.4 Test Project Components

```bash
# Test document processor
python3 -c "from mongo_manager import MongoManager; print('MongoDB manager imported successfully')"

# Test API (if you have chat_api.py)
# python3 chat_api.py
```

---

## Step 9: Set Up Services (Optional)

### 9.1 Create Systemd Service for API

```bash
# Create service file
sudo nano /etc/systemd/system/qppchatbot.service
```

Add the following content:

```ini
[Unit]
Description=QPPChatbot API Service
After=network.target mongod.service postgresql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/qppchatbot
Environment="PATH=/opt/qppchatbot/venv/bin"
ExecStart=/opt/qppchatbot/venv/bin/python3 chat_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable qppchatbot

# Start service
sudo systemctl start qppchatbot

# Check status
sudo systemctl status qppchatbot
```

### 9.2 Set Up Nginx Reverse Proxy (Optional)

```bash
# Install Nginx
sudo apt install -y nginx

# Check Nginx version
nginx -v

# Start and enable Nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Create Nginx configuration
sudo nano /etc/nginx/sites-available/qppchatbot
```

Add configuration:

```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    # API backend
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend
    location / {
        root /opt/qppchatbot/chat-companion-hub/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/qppchatbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Troubleshooting

### MongoDB Connection Issues

```bash
# Check if MongoDB is running
sudo systemctl status mongod

# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log

# Test MongoDB connection
mongosh --eval "db.adminCommand('ping')"

# Check MongoDB port
sudo netstat -tlnp | grep 27017
```

### Permission Issues

```bash
# Fix MongoDB data directory permissions
sudo chown -R mongodb:mongodb /var/lib/mongodb
sudo chown -R mongodb:mongodb /var/log/mongodb

# Fix project directory permissions
sudo chown -R $USER:$USER /opt/qppchatbot

# Fix MongoDB service if it fails to start
sudo systemctl daemon-reload
sudo systemctl restart mongod
```

### Ubuntu-Specific Issues

```bash
# If MongoDB installation fails, check Ubuntu version compatibility
lsb_release -a

# For Ubuntu 20.04, you might need to use MongoDB 6.0 instead of 7.0
# Update the repository URL accordingly

# Check if MongoDB service exists
sudo systemctl list-unit-files | grep mongod

# View MongoDB service logs
sudo journalctl -u mongod -n 50
```

### Python Import Errors

```bash
# Ensure virtual environment is activated
source /opt/qppchatbot/venv/bin/activate

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"
```

### Database Import Issues

```bash
# Check if database exists
mongosh --eval "show dbs"

# Drop and re-import if needed
mongosh --eval "use legal_cases_v2; db.dropDatabase()"
mongorestore --db legal_cases_v2 /tmp/mongodb_export_*/legal_cases_v2
```

### Network Access Issues

If you need to access MongoDB from outside the VM:

1. Update `/etc/mongod.conf`:
   ```yaml
   net:
     bindIp: 0.0.0.0
   ```

2. Configure firewall:
   ```bash
   sudo ufw allow 27017/tcp
   ```

3. Restart MongoDB:
   ```bash
   sudo systemctl restart mongod
   ```

---

## Verification Checklist

After migration, verify:

- [ ] MongoDB is running and accessible
- [ ] All collections imported successfully
- [ ] Document counts match original database
- [ ] Python virtual environment is set up
- [ ] All dependencies installed
- [ ] Configuration files updated
- [ ] MongoDB connection test passes
- [ ] PostgreSQL is running (if used)
- [ ] Storage directories created
- [ ] API/service starts successfully (if applicable)
- [ ] Frontend builds and runs (if applicable)

---

## Quick Reference Commands

```bash
# MongoDB
sudo systemctl status mongod
sudo systemctl restart mongod
mongosh
mongodump --db legal_cases_v2 --out /backup
mongorestore --db legal_cases_v2 /backup/legal_cases_v2

# Export/Import Scripts (on local machine)
cd /Users/gwl/Desktop/QPPChatbot
./scripts/export_mongodb.sh

# Export/Import Scripts (on VM)
cd /opt/qppchatbot
./scripts/import_mongodb.sh /tmp/mongodb_export_*/

# Project
cd /opt/qppchatbot
source venv/bin/activate
python3 test_mongodb_connection.py

# Services
sudo systemctl status qppchatbot
sudo journalctl -u qppchatbot -f
```

---

## Additional Notes

1. **Backup Strategy**: Set up regular MongoDB backups on the VM:
   ```bash
   # Add to crontab
   0 2 * * * mongodump --db legal_cases_v2 --out /backup/mongodb_$(date +\%Y\%m\%d)
   ```

2. **Security**: 
   - Enable MongoDB authentication
   - Use strong passwords
   - Configure firewall rules
   - Keep system updated

3. **Monitoring**: Consider setting up monitoring for:
   - MongoDB performance
   - Disk space
   - Application logs

4. **SSL/TLS**: For production, set up SSL certificates for secure connections

---

**Last Updated**: 2025-01-27  
**Version**: 1.0.0

