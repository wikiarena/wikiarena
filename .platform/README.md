# Platform Hooks for Wiki Arena

This directory contains Elastic Beanstalk Platform Hooks that run during application deployment.

## Directory Structure

```
.platform/
├── hooks/
│   └── prebuild/           # Runs after source extraction, before app setup
│       └── 01_database_setup.sh
└── README.md
```

## Hook Execution Order

1. **prebuild/** - After EB extracts source bundle, before app/web server setup
2. **predeploy/** - After app setup, before starting application  
3. **postdeploy/** - After application is running

## Database Setup Hook

**File:** `hooks/prebuild/01_database_setup.sh`

**Purpose:** Downloads the 33GB Wikipedia database from S3 and sets it up for the solver.

**Key Features:**
- ✅ Runs as root (no permission issues)
- ✅ Access to EB environment variables via `get-config`
- ✅ Fails deployment if database setup fails
- ✅ Skips download if database already exists
- ✅ Logs everything to `/var/log/wiki-arena-database-setup.log`

**Environment Variables Used:**
- `DATABASE_S3_BUCKET` - S3 bucket containing `wiki_graph.sqlite.gz`

**Output:**
- Downloads database to `/var/app/database/wiki_graph.sqlite`
- Sets proper permissions for `webapp` user
- Performs basic integrity check

## Deployment Process

1. **Package:** Your application code + `.platform/` is zipped
2. **Deploy:** EB extracts bundle on EC2 instance
3. **prebuild:** `01_database_setup.sh` downloads database from S3  
4. **Setup:** EB configures app and web server
5. **Start:** Application starts with database ready

## Debugging

**View hook logs:**
```bash
sudo tail -f /var/log/wiki-arena-database-setup.log
```

**Check database status:**
```bash
ls -la /var/app/database/
du -h /var/app/database/wiki_graph.sqlite
```

**Verify EB environment variables:**
```bash
/opt/elasticbeanstalk/bin/get-config environment -k DATABASE_S3_BUCKET
```

## Benefits vs Other Approaches

**vs User Data:**
- ✅ Works with Elastic Beanstalk (User Data doesn't)
- ✅ Version controlled with application code
- ✅ Access to EB environment variables

**vs Application Code:**
- ✅ Runs as root (no permission issues)  
- ✅ Happens before app starts (no startup delays)
- ✅ Proper separation of infrastructure vs application concerns