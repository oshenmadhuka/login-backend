# in backend folder.
# main.js
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from pymongo import MongoClient
from datetime import datetime, timedelta
import jwt
from jwt import PyJWTError
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import joblib
import pandas as pd

app = FastAPI()

class PredictionRequest(BaseModel):
    date: str

class PredictionResponse(BaseModel):
    date: str
    predicted_attendance: int

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://polite-glacier-0649dff0f.5.azurestaticapps.net"],  # Update with your frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Allow all methods
    allow_headers=["*"],
)
client = MongoClient("mongodb+srv://oshen:oshen@cluster0.h2my8yk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["Loginbase"]
collection = db["logins"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "1234"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class User(BaseModel):
    username: str
    password: str

class UserInDB(BaseModel):
    username: str
    hashed_password: str

def get_user(username: str):
    user_data = collection.find_one({"username": username})
    if user_data:
        return UserInDB(**user_data)
    else:
        return None

def authenticate_user(username: str, password: str):
    user_data = collection.find_one({"username": username})
    if user_data and pwd_context.verify(password, user_data["hashed_password"]):
        print(f"user:{user_data}")
        return UserInDB(**user_data)
    
    return None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id : int = payload.get('id')
        if username is None or user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {'username':username, 'id':user_id}
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/signup")
async def signup(user: User):
    hashed_password = pwd_context.hash(user.password)
    user_data = {"username": user.username, "hashed_password": hashed_password}
    try:
        collection.insert_one(user_data)  # Insert user data into MongoDB
        return {"message": "User signed up successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error signing up: {str(e)}")
    

    
@app.get("/token")  # Allow GET requests for token retrieval
async def get_token(username: str, password: str):
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    print(f"Received login request with username: {form_data.username}, password: {form_data.password}")  # Log received data
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        print("Authentication failed")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        # Log hashed password from database
        print(f"Hashed password from database: {user.hashed_password}")

        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
            data={"sub": form_data.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token}
    except Exception as e:
        print(f"Error generating token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")




@app.get("/users/me")
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

@app.post("/predict/")
async def predict_attendance(request: PredictionRequest):
    try:
        # Load the machine learning model
        rf_model = joblib.load("random_forest_regression_model3_month.joblib")

        # Predict attendance for the given date
        future_data = create_future_data(request.date)
        predicted_attendance = rf_model.predict(future_data)
        predicted_attendance_rounded = int(round(predicted_attendance[0]))  # Round to nearest integer

        # Establish MongoDB connection
        client = AsyncIOMotorClient("mongodb+srv://oshen:oshen@cluster0.h2my8yk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
        db = client["attendance_db"]
        collection = db["predictions"]

        # Store prediction in MongoDB
        await collection.insert_one({"date": request.date, "predicted_attendance": predicted_attendance_rounded})

        return {"predicted_attendance": predicted_attendance_rounded}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict/chart/")
async def predict_attendance_chart(request: PredictionRequest):
    try:
        # Load the machine learning model
        rf_model = joblib.load("random_forest_regression_model3_month.joblib")

        # Convert the input date to a datetime object
        input_date = datetime.strptime(request.date, '%m%d')

        # Create data for the next 7 days
        prediction_data = []
        for i in range(1, 8):
            next_date = (input_date + timedelta(days=i)).strftime('%m%d')
            future_data = create_future_data(next_date)
            predicted_attendance = rf_model.predict(future_data)
            predicted_attendance_rounded = int(round(predicted_attendance[0]))  # Round to nearest integer
            prediction_data.append({"date": next_date, "predicted_attendance": predicted_attendance_rounded})

        return prediction_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def is_holiday(date):
    future_holidays = {
        "0115": "Tamil Thai Pongal Day",
        "0125": "Duruthu Full Moon Poya Day",
        "0204": "Independence Day",
        "0223": "Navam Full Moon Poya Day",
        "0308": "Mahasivarathri Day",
        "0324": "Medin Full Moon Poya Day",
        "0329": "Good Friday",
        "0411": "Id-Ul-Fitr (Ramazan Festival Day)",
        "0412": "Day prior to Sinhala & Tamil New Year Day",
        "0413": "Sinhala & Tamil New Year Day",
        "0423": "Bak Full Moon Poya Day",
        "0501": "May Day (International Workers Day)",
        "0523": "Vesak Full Moon Poya Day",
        "0524": "Day following Vesak Full Moon Poya Day",
        "0617": "Id-Ul-Alha (Hadji Festival Day)",
        "0621": "Poson Full Moon Poya Day",
        "0720": "Esala Full Moon Poya Day",
        "0819": "Nikini Full Moon Poya Day",
        "0916": "Milad-Un-Nabi (Holy Prophet's Birthday)",
        "0917": "Binara Full Moon Poya Day",
        "1017": "Vap Full Moon Poya Day",
        "1031": "Deepavali Festival Day",
        "1115": "Ill Full Moon Poya Day",
        "1214": "Unduvap Full Moon Poya Day",
        "1225": "Christmas Day"
    }

    if date in future_holidays.keys():
        return 1
    else:
        return 0

def create_future_data(date):
    future_date_datetime = pd.to_datetime(date, format='%m%d', errors='raise')
    print("Input Date:", future_date_datetime)

    next_day = future_date_datetime + pd.DateOffset(days=1)
    previous_day = future_date_datetime - pd.DateOffset(days=1)
    print("Next Day:", next_day)
    print("Previous Day:", previous_day)

    next_day_holiday = is_holiday(next_day.strftime("%m%d"))
    previous_day_holiday = is_holiday(previous_day.strftime("%m%d"))
    print("Next Day Holiday:", next_day_holiday)
    print("Previous Day Holiday:", previous_day_holiday)

    is_holiday_flag = 1 if is_holiday(date) else 0
    print("Is Holiday Flag:", is_holiday_flag)

    day_of_week = future_date_datetime.dayofweek
    print("Day of the Week:", day_of_week)

    if previous_day.dayofweek == 6 and next_day_holiday:
        previous_day_holiday = 1

    future_data = pd.DataFrame({
        "Previous day is a holiday": [previous_day_holiday],
        "Is Holiday": [is_holiday_flag],
        "Next day is a holiday": [next_day_holiday],
        "Day of the week": [day_of_week]
    })

    return future_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
