from fastapi import FastAPI
import random
import uvicorn

app = FastAPI()

#generate random numbers
@app.get("/get_number")
async def root():
    number = random.randint(0,10000000)
    return {"number": number}

if __name__ == "__main__":
    uvicorn.run(app)