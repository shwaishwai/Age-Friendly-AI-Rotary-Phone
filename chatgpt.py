from openai import OpenAI

 

client = OpenAI( 

    api_key = "" 

) 

 

messages = [ 

    { 

        "role": "system", 

        "content": "You are a helpful assistant" 

    } 

] 

 

while True: 

    message = input("You: ") 

 

    messages.append( 

        { 

            "role": "user", 

            "content": message 

        }, 

    ) 

 

    chat = client.chat.completions.create( 

        messages=messages, 

        model="gpt-3.5-turbo" 

    ) 

 

    reply = chat.choices[0].message 

 

    print("Assistant: ", reply.content) 

     

    messages.append(reply) 
