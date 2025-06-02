# simple ekg monitor

This is a simple EKG monitor application that reads data from an EKG device using the serial port and displays the data in real-time using matplotlib.

## creating app

create main.py file
create README.md file
create .gitignore file

### git init

```bash
git init
git add .
git commit -m "initial commit"

```

### create virtual environment

```bash
python -m venv env
```

### activate virtual environment

```bash
source env/Scripts/activate
```

### install dependencies

```bash
pip install pyserial matplotlib numpy pandas
```

### create requirements.txt

```bash
pip freeze > requirements.txt
```

### deactivate virtual environment

```bash
deactivate
```

## clone app

instll from requirements.txt

```bash
pip install -r requirements.txt
```
